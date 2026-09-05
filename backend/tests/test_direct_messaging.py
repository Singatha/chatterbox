from httpx import AsyncClient


async def register_user(client: AsyncClient, username: str) -> dict:
    response = await client.post(
        "/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 201
    return response.json()


def auth_headers(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


async def create_direct(
    client: AsyncClient, owner: dict, participant: dict
) -> dict:
    response = await client.post(
        "/conversations",
        headers=auth_headers(owner),
        json={"participant_id": participant["user"]["id"]},
    )
    assert response.status_code == 201
    return response.json()


async def test_user_search_requires_auth_and_excludes_current_user(client: AsyncClient) -> None:
    alice = await register_user(client, "alice")
    await register_user(client, "alicia")
    await register_user(client, "bob")

    unauthorized = await client.get("/users?q=ali")
    response = await client.get("/users?q=ali", headers=auth_headers(alice))

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert [item["username"] for item in response.json()] == ["alicia"]
    assert "email" not in response.json()[0]


async def test_direct_conversation_is_idempotent_and_visible_to_both_members(
    client: AsyncClient,
) -> None:
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")

    first = await create_direct(client, alice, bob)
    second = await create_direct(client, bob, alice)
    alice_list = await client.get("/conversations", headers=auth_headers(alice))
    bob_list = await client.get("/conversations", headers=auth_headers(bob))

    assert first["id"] == second["id"]
    assert {member["username"] for member in first["members"]} == {"alice", "bob"}
    assert [item["id"] for item in alice_list.json()] == [first["id"]]
    assert [item["id"] for item in bob_list.json()] == [first["id"]]


async def test_cannot_start_conversation_with_self(client: AsyncClient) -> None:
    alice = await register_user(client, "alice")

    response = await client.post(
        "/conversations",
        headers=auth_headers(alice),
        json={"participant_id": alice["user"]["id"]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PARTICIPANT"


async def test_non_member_cannot_read_or_send_messages(client: AsyncClient) -> None:
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    mallory = await register_user(client, "mallory")
    conversation = await create_direct(client, alice, bob)
    path = f"/conversations/{conversation['id']}/messages"

    read = await client.get(path, headers=auth_headers(mallory))
    send = await client.post(
        path, headers=auth_headers(mallory), json={"content": "not allowed"}
    )

    assert read.status_code == 403
    assert send.status_code == 403
    assert read.json()["error"]["code"] == "CONVERSATION_ACCESS_DENIED"


async def test_send_and_retrieve_message_history(client: AsyncClient) -> None:
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    conversation = await create_direct(client, alice, bob)
    path = f"/conversations/{conversation['id']}/messages"

    sent = await client.post(
        path, headers=auth_headers(alice), json={"content": "  Hello Bob  "}
    )
    history = await client.get(path, headers=auth_headers(bob))
    conversations = await client.get("/conversations", headers=auth_headers(bob))

    assert sent.status_code == 201
    assert sent.json()["content"] == "Hello Bob"
    assert sent.json()["sender_username"] == "alice"
    assert history.status_code == 200
    assert [item["content"] for item in history.json()["items"]] == ["Hello Bob"]
    assert conversations.json()[0]["last_message"]["content"] == "Hello Bob"


async def test_message_history_uses_cursor_pagination(client: AsyncClient) -> None:
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    conversation = await create_direct(client, alice, bob)
    path = f"/conversations/{conversation['id']}/messages"
    for index in range(6):
        response = await client.post(
            path,
            headers=auth_headers(alice),
            json={"content": f"message-{index}"},
        )
        assert response.status_code == 201

    newest = await client.get(f"{path}?limit=2", headers=auth_headers(alice))
    older = await client.get(
        f"{path}?limit=2&before={newest.json()['next_cursor']}",
        headers=auth_headers(alice),
    )

    assert [item["content"] for item in newest.json()["items"]] == [
        "message-4",
        "message-5",
    ]
    assert [item["content"] for item in older.json()["items"]] == [
        "message-2",
        "message-3",
    ]
    assert newest.json()["next_cursor"]
    assert older.json()["next_cursor"]


async def test_message_history_recovers_records_after_cursor(client: AsyncClient) -> None:
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    conversation = await create_direct(client, alice, bob)
    path = f"/conversations/{conversation['id']}/messages"
    first = await client.post(
        path, headers=auth_headers(alice), json={"content": "online"}
    )
    cursor = first.json()["cursor"]
    await client.post(path, headers=auth_headers(bob), json={"content": "missed one"})
    await client.post(path, headers=auth_headers(bob), json={"content": "missed two"})

    recovered = await client.get(
        f"{path}?after={cursor}", headers=auth_headers(alice)
    )

    assert recovered.status_code == 200
    assert [item["content"] for item in recovered.json()["items"]] == [
        "missed one",
        "missed two",
    ]


async def test_before_and_after_cursors_are_mutually_exclusive(client: AsyncClient) -> None:
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    conversation = await create_direct(client, alice, bob)
    path = f"/conversations/{conversation['id']}/messages"
    sent = await client.post(path, headers=auth_headers(alice), json={"content": "one"})
    cursor = sent.json()["cursor"]

    response = await client.get(
        f"{path}?before={cursor}&after={cursor}", headers=auth_headers(alice)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_CURSOR"


async def test_invalid_cursor_and_blank_message_are_rejected(client: AsyncClient) -> None:
    alice = await register_user(client, "alice")
    bob = await register_user(client, "bob")
    conversation = await create_direct(client, alice, bob)
    path = f"/conversations/{conversation['id']}/messages"

    invalid_cursor = await client.get(
        f"{path}?before=invalid", headers=auth_headers(alice)
    )
    blank = await client.post(
        path, headers=auth_headers(alice), json={"content": "   "}
    )

    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["error"]["code"] == "INVALID_CURSOR"
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "VALIDATION_ERROR"
