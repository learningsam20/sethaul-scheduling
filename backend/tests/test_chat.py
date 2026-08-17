from app.services import chat


def test_duplicate_driver_message_flagged(db):
    thread = chat.create_thread("DRV006", "SHP1006")
    first = chat.add_message(thread["thread_id"], "DRIVER", "Traffic after Shahpura unique test 42", "DRV006")
    second = chat.add_message(thread["thread_id"], "DRIVER", "Traffic after Shahpura unique test 42", "DRV006")
    assert first.get("is_duplicate") == 0
    assert second.get("is_duplicate") == 1


def test_greeting_is_not_a_delay_duplicate(db):
    thread = chat.create_thread("DRV006", "SHP1006")
    first = chat.add_message(thread["thread_id"], "DRIVER", "hi", "DRV006")
    other = chat.create_thread("DRV006", "SHP1007")
    second = chat.add_message(other["thread_id"], "DRIVER", "hi", "DRV006")
    assert first.get("is_duplicate") == 0
    assert second.get("is_duplicate") == 0
