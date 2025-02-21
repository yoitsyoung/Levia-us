from memory.vector_db_provider.pinecone.pinecone import PineconeDb
from datetime import datetime
import time
vector_db = PineconeDb(index_name="levia")


def save_memory(id: str, vector: list, metadata: dict, namespace: str):
    metadata["timestamp"] = int(datetime.now().timestamp() * 1000)
    input_embedding = {
        "id": id,
        "values": vector,
        "metadata": metadata,
    }
    try:
        vector_db.upsert([input_embedding], namespace)
    except Exception as e:
        raise Exception(f"Error saving memory: {str(e)}")

def retrieve_memory(vector: list, namespace: str, top_k: int = 10):
    memories = vector_db.query(
        vector=vector,
        namespace=namespace,
        top_k=top_k,
        include_metadata=True,
        include_values=False,
    )
    return memories

def delete_memory(id: str, namespace: str):
    vector_db.delete(id, namespace)
