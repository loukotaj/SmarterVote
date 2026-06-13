from google.cloud import firestore

def main():
    conversation_id = "1fdee39f-57f8-4f68-a861-aee66028a7f0"
    db = firestore.Client()

    messages = list(db.collection("admin_agent_messages").where("conversation_id", "==", conversation_id).stream())
    messages = sorted(messages, key=lambda m: m.to_dict().get("created_at") or "")

    print(f"Found {len(messages)} messages:")
    for m in messages:
        d = m.to_dict()
        role = d.get("role")
        created_at = d.get("created_at")
        content = d.get("content")
        print(f"[{created_at}] {role}:")
        # Print first line of content
        first_line = content.split("\n")[0][:100]
        print(f"  {first_line}...")
        print("-" * 50)

if __name__ == "__main__":
    main()
