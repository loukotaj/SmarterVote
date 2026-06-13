import sys
from google.cloud import firestore

def main():
    conversation_id = "1fdee39f-57f8-4f68-a861-aee66028a7f0"
    db = firestore.Client()

    print("--- CONVERSATION ---")
    conv_doc = db.collection("admin_agent_conversations").document(conversation_id).get()
    if not conv_doc.exists:
        print(f"Conversation {conversation_id} not found.")
        return
    print(conv_doc.to_dict())

    print("\n--- TASKS ---")
    tasks = list(db.collection("admin_agent_tasks").where("conversation_id", "==", conversation_id).stream())
    print(f"Found {len(tasks)} tasks.")
    for task in tasks:
        print(f"Task ID: {task.id}")
        print(task.to_dict())

    print("\n--- MESSAGES ---")
    messages = list(db.collection("admin_agent_messages").where("conversation_id", "==", conversation_id).stream())
    messages = sorted(messages, key=lambda m: m.to_dict().get("created_at") or "")
    print(f"Found {len(messages)} messages.")
    for msg in messages:
        d = msg.to_dict()
        role = d.get("role")
        content = d.get("content")
        created_at = d.get("created_at")
        task_id = d.get("task_id")
        print(f"[{created_at}] {role} (task: {task_id}):")
        print(f"  {content}")
        metadata = d.get("metadata")
        if metadata:
            print(f"  Metadata: {metadata}")
        print("-" * 40)

if __name__ == "__main__":
    main()
