import requests
import time


API_KEY = "sk-prod-abc123secret"
BASE_URL = "https://api.example.com/v1"


def fetch_user_data(user_id):
    response = requests.get(
        f"{BASE_URL}/users/{user_id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    data = response.json()
    return data


def update_user(user_id, payload):
    response = requests.put(
        f"{BASE_URL}/users/{user_id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=payload,
    )
    return response.json()


def delete_all_users(user_ids):
    for uid in user_ids:
        requests.delete(
            f"{BASE_URL}/users/{uid}",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )
        time.sleep(0.1)
    return True


if __name__ == "__main__":
    user = fetch_user_data(42)
    print(user)
    update_user(42, {"name": "test"})
    delete_all_users([1, 2, 3])
