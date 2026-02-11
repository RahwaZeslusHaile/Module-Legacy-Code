import json
import sys
import requests

from typing import Any, Dict, Optional


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(1)


def post(endpoint: str, data: Dict[str, Any], access_token: Optional[str] = None):
    headers = {
        "Content-Type": "application/json",
    }
    if access_token is not None:
        headers["Authorization"] = f"Bearer {access_token}"
    response = requests.post(
        f"http://127.0.0.1:3000{endpoint}", data=json.dumps(data), headers=headers
    )
    if response.status_code != 200:
        fail(
            f"Got status code {response.status_code} from request to {endpoint}. Response body: {response.text}"
        )
    return response.json()


def create_user(username: str, password: str) -> str:
    """create_user creates a user and returns an access token which can be used for future requests."""
    response = post("/register", data={"username": username, "password": password})
    if not response["success"]:
        fail(f"Could not create user: {response}")
    return response["token"]


def send_bloom(access_token: str, text: str) -> None:
    post("/bloom", data={"content": text}, access_token=access_token)


def follow(*, follower_access_token: str, follow_username: str) -> None:
    post(
        "/follow",
        data={"follow_username": follow_username},
        access_token=follower_access_token,
    )


def main():
    sample_access_token = create_user("sample", "sosecret")
    send_bloom(sample_access_token, "Hi there")

    tech_influencer_access_token = create_user("TechInfluencer", "Crypto4Lyfe")
    send_bloom(tech_influencer_access_token, "Tech is magic #blessed #TechLife")

    musician_access_token = create_user("Swiz", "singingalldayeveryday")
    send_bloom(
        musician_access_token, "New album dropping at midnight! Pre-save now! #SwizBiz"
    )
    send_bloom(musician_access_token, "Let's get some #SwizBiz love!!")

    send_bloom(sample_access_token, "I'm not quite sure how this works")

    writer_access_token = create_user("AS", "neverSt0pTalking")
    send_bloom(
        writer_access_token,
        "Marshmallows are magnificent! They have great squish and taste amazing. Toast them until they're golden and slightly melted. Simply delicious!",
    )

    justsomeguy_access_token = create_user("JustSomeGuy", "mysterious")
    send_bloom(justsomeguy_access_token, "Hello.")

    for other_user in ["OtherUser", "Lurker", "SomeQuietMongoose"]:
        create_user(other_user, "PleaseDon'tStealMe")

    follow(follower_access_token=sample_access_token, follow_username="TechInfluencer")
    follow(follower_access_token=sample_access_token, follow_username="Swiz")
    follow(follower_access_token=sample_access_token, follow_username="AS")
    follow(follower_access_token=musician_access_token, follow_username="sample")


if __name__ == "__main__":
    main()
