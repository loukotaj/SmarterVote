from google.cloud import firestore

def main():
    conversation_id = "1fdee39f-57f8-4f68-a861-aee66028a7f0"
    db = firestore.Client()

    print("--- CONVERSATION ---")
    conv_doc = db.collection("admin_agent_conversations").document(conversation_id).get()
    if not conv_doc.exists:
        print("Not found.")
        return
    print(conv_doc.to_dict())

    print("\n--- TASKS ---")
    tasks = list(db.collection("admin_agent_tasks").where("conversation_id", "==", conversation_id).stream())
    print(f"Found {len(tasks)} tasks.")
    for task in tasks:
        d = task.to_dict()
        print(f"Task ID: {task.id}")
        print(f"  Status: {d.get('status')}")
        print(f"  Iteration: {d.get('iteration')}")
        print(f"  Continuation Count: {d.get('continuation_count')}")
        print(f"  Created At: {d.get('created_at')}")
        print(f"  Updated At: {d.get('updated_at')}")
        print(f"  Started At: {d.get('started_at')}")
        print(f"  Pending Tool Call: {d.get('pending_tool_call')}")
        print(f"  Error: {d.get('error')}")
        print(f"  Cancel Requested: {d.get('cancel_requested')}")
        print("-" * 30)

if __name__ == "__main__":
    main()
