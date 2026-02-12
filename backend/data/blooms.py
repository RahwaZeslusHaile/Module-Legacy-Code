import datetime

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from data.connection import db_cursor
from data.users import User


@dataclass
class Bloom:
    id: int
    sender: User
    content: str
    sent_timestamp: datetime.datetime
    rebloom_count: int = 0
    rebloomed_by: Optional[str] = None  
    rebloom_timestamp: Optional[datetime.datetime] = None


def add_bloom(*, sender: User, content: str) -> Bloom:
    hashtags = [word[1:] for word in content.split(" ") if word.startswith("#")]

    now = datetime.datetime.now(tz=datetime.UTC)
    bloom_id = int(now.timestamp() * 1000000)
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO blooms (id, sender_id, content, send_timestamp) VALUES (%(bloom_id)s, %(sender_id)s, %(content)s, %(timestamp)s)",
            dict(
                bloom_id=bloom_id,
                sender_id=sender.id,
                content=content,
                timestamp=datetime.datetime.now(datetime.UTC),
            ),
        )
        for hashtag in hashtags:
            cur.execute(
                "INSERT INTO hashtags (hashtag, bloom_id) VALUES (%(hashtag)s, %(bloom_id)s)",
                dict(hashtag=hashtag, bloom_id=bloom_id),
            )


def get_blooms_for_user(
    username: str, *, before: Optional[int] = None, limit: Optional[int] = None
) -> List[Bloom]:
    with db_cursor() as cur:
        kwargs = {
            "sender_username": username,
        }
        if before is not None:
            before_clause = "AND send_timestamp < %(before_limit)s"
            kwargs["before_limit"] = before
        else:
            before_clause = ""

        limit_clause = make_limit_clause(limit, kwargs)

        cur.execute(
            f"""
            WITH rebloom_counts AS (
                SELECT bloom_id, COUNT(*) as count
                FROM reblooms
                GROUP BY bloom_id
            )
            SELECT
              blooms.id, users.username, content, send_timestamp, COALESCE(rc.count, 0) as rebloom_count
            FROM
              blooms 
              INNER JOIN users ON users.id = blooms.sender_id
              LEFT JOIN rebloom_counts rc ON blooms.id = rc.bloom_id
            WHERE
              username = %(sender_username)s
              {before_clause}
            ORDER BY send_timestamp DESC
            {limit_clause}
            """,
            kwargs,
        )
        rows = cur.fetchall()
        blooms = []
        for row in rows:
            bloom_id, sender_username, content, timestamp, rebloom_count = row
            blooms.append(
                Bloom(
                    id=bloom_id,
                    sender=sender_username,
                    content=content,
                    sent_timestamp=timestamp,
                    rebloom_count=rebloom_count,
                )
            )
    return blooms


def get_bloom(bloom_id: int) -> Optional[Bloom]:
    with db_cursor() as cur:
        cur.execute(
            """
            WITH rebloom_counts AS (
                SELECT bloom_id, COUNT(*) as count
                FROM reblooms
                GROUP BY bloom_id
            )
            SELECT blooms.id, users.username, content, send_timestamp, COALESCE(rc.count, 0) as rebloom_count
            FROM blooms 
            INNER JOIN users ON users.id = blooms.sender_id
            LEFT JOIN rebloom_counts rc ON blooms.id = rc.bloom_id
            WHERE blooms.id = %s
            """,
            (bloom_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        bloom_id, sender_username, content, timestamp, rebloom_count = row
        return Bloom(
            id=bloom_id,
            sender=sender_username,
            content=content,
            sent_timestamp=timestamp,
            rebloom_count=rebloom_count,
        )


def get_blooms_with_hashtag(
    hashtag_without_leading_hash: str, *, limit: int = None
) -> List[Bloom]:
    kwargs = {
        "hashtag_without_leading_hash": hashtag_without_leading_hash,
    }
    limit_clause = make_limit_clause(limit, kwargs)
    with db_cursor() as cur:
        cur.execute(
            f"""
            WITH rebloom_counts AS (
                SELECT bloom_id, COUNT(*) as count
                FROM reblooms
                GROUP BY bloom_id
            )
            SELECT
              blooms.id, users.username, content, send_timestamp, COALESCE(rc.count, 0) as rebloom_count
            FROM
              blooms 
              INNER JOIN hashtags ON blooms.id = hashtags.bloom_id 
              INNER JOIN users ON blooms.sender_id = users.id
              LEFT JOIN rebloom_counts rc ON blooms.id = rc.bloom_id
            WHERE
              hashtag = %(hashtag_without_leading_hash)s
            ORDER BY send_timestamp DESC
            {limit_clause}
            """,
            kwargs,
        )
        rows = cur.fetchall()
        blooms = []
        for row in rows:
            bloom_id, sender_username, content, timestamp, rebloom_count = row
            blooms.append(
                Bloom(
                    id=bloom_id,
                    sender=sender_username,
                    content=content,
                    sent_timestamp=timestamp,
                    rebloom_count=rebloom_count,
                )
            )
    return blooms


def make_limit_clause(limit: Optional[int], kwargs: Dict[Any, Any]) -> str:
    if limit is not None:
        limit_clause = "LIMIT %(limit)s"
        kwargs["limit"] = limit
    else:
        limit_clause = ""
    return limit_clause


def add_rebloom(*, user: User, bloom_id: int) -> bool:
    """Add a rebloom for a user. Returns True if successful, False if already rebloomed."""
    with db_cursor() as cur:
        # Check if bloom exists
        cur.execute("SELECT id FROM blooms WHERE id = %s", (bloom_id,))
        if cur.fetchone() is None:
            raise ValueError(f"Bloom {bloom_id} does not exist")
        
        # Check if user already rebloomed this
        cur.execute(
            "SELECT id FROM reblooms WHERE user_id = %(user_id)s AND bloom_id = %(bloom_id)s",
            dict(user_id=user.id, bloom_id=bloom_id)
        )
        if cur.fetchone() is not None:
            return False  # Already rebloomed
        
        # Add the rebloom
        cur.execute(
            "INSERT INTO reblooms (user_id, bloom_id, rebloom_timestamp) VALUES (%(user_id)s, %(bloom_id)s, %(timestamp)s)",
            dict(
                user_id=user.id,
                bloom_id=bloom_id,
                timestamp=datetime.datetime.now(datetime.UTC)
            )
        )
        return True


def get_rebloom_count(bloom_id: int) -> int:
    """Get the number of times a bloom has been rebloomed."""
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM reblooms WHERE bloom_id = %s", (bloom_id,))
        return cur.fetchone()[0]


def get_timeline_blooms_for_user(user: User, *, limit: int = None) -> List[Bloom]:
    """
    Get blooms for a user's timeline including:
    1. Their own blooms
    2. Blooms from users they follow
    3. Reblooms from users they follow (with rebloom metadata)
    
    Returns blooms sorted by timestamp (original or rebloom timestamp) descending.
    """
    kwargs = {"user_id": user.id}
    limit_clause = make_limit_clause(limit, kwargs)
    
    with db_cursor() as cur:
        # Get all blooms (own + followed) with rebloom counts and metadata
        cur.execute(
            f"""
            WITH followed AS (
                SELECT followee_id FROM follows WHERE follower_id = %(user_id)s
            ),
            rebloom_counts AS (
                SELECT bloom_id, COUNT(*) as count
                FROM reblooms
                GROUP BY bloom_id
            )
            -- Original blooms from self and followed users
            SELECT 
                b.id,
                u.username,
                b.content,
                b.send_timestamp,
                COALESCE(rc.count, 0) as rebloom_count,
                NULL as rebloomed_by,
                b.send_timestamp as display_timestamp
            FROM blooms b
            JOIN users u ON b.sender_id = u.id
            LEFT JOIN rebloom_counts rc ON b.id = rc.bloom_id
            WHERE b.sender_id = %(user_id)s OR b.sender_id IN (SELECT followee_id FROM followed)
            
            UNION ALL
            
            -- Reblooms from followed users
            SELECT 
                b.id,
                original_user.username,
                b.content,
                b.send_timestamp,
                COALESCE(rc.count, 0) as rebloom_count,
                rebloomer.username as rebloomed_by,
                r.rebloom_timestamp as display_timestamp
            FROM reblooms r
            JOIN blooms b ON r.bloom_id = b.id
            JOIN users original_user ON b.sender_id = original_user.id
            JOIN users rebloomer ON r.user_id = rebloomer.id
            LEFT JOIN rebloom_counts rc ON b.id = rc.bloom_id
            WHERE r.user_id IN (SELECT followee_id FROM followed)
            
            ORDER BY display_timestamp DESC
            {limit_clause}
            """,
            kwargs
        )
        
        rows = cur.fetchall()
        blooms = []
        for row in rows:
            bloom_id, sender_username, content, sent_timestamp, rebloom_count, rebloomed_by, display_timestamp = row
            blooms.append(
                Bloom(
                    id=bloom_id,
                    sender=sender_username,
                    content=content,
                    sent_timestamp=sent_timestamp,
                    rebloom_count=rebloom_count,
                    rebloomed_by=rebloomed_by,
                    rebloom_timestamp=display_timestamp if rebloomed_by else None
                )
            )
        return blooms
