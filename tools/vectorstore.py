import threading
from pymongo import MongoClient
from sentence_transformers import SentenceTransformer
import pinecone
from bson.objectid import ObjectId


class VectorStore:
    def __init__(self, mongo_uri, mongo_db, mongo_collection, pinecone_api_key, pinecone_index_name, pinecone_env='us-east-1-gcp-free', embedding_model_name='sentence-transformers/all-MiniLM-L6-v2'):
        # Initialize MongoDB connection
        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client[mongo_db]
        self.collection = self.db[mongo_collection]
        
        # Initialize Pinecone
        pinecone.init(api_key=pinecone_api_key, environment=pinecone_env)
        if pinecone_index_name not in pinecone.list_indexes():
            pinecone.create_index(pinecone_index_name, dimension=384)  # Adjust the dimension as needed
        self.pinecone_index = pinecone.Index(pinecone_index_name)

        # Load the embedding model
        self.embedding_model = SentenceTransformer(embedding_model_name)

    def insert_documents(self, data):
        """Insert a list of documents into the MongoDB collection."""
        documents = data.to_dict("records")
        self.collection.insert_many(documents)
        print(f"Inserted {len(documents)} documents into MongoDB.")

    def encode_text(self, text):
        """Convert text to a vector using the embedding model."""
        vector = self.embedding_model.encode(text).tolist()
        return [float(x) for x in vector]  # Ensure elements are float

    def handle_change(self, change):
        """Handle MongoDB change events."""
        operation_type = change['operationType']
        if operation_type == 'insert':
            document = change['fullDocument']
            vector = self.encode_text(document['fullplot'])
            self.pinecone_index.upsert([(str(document['_id']), vector)])
        elif operation_type == 'update':
            document = change['fullDocument']
            updated_fields = change['updateDescription']['updatedFields']
            if 'fullplot' in updated_fields:
                vector = self.encode_text(updated_fields['fullplot'])
                self.pinecone_index.upsert([(str(document['_id']), vector)])
        elif operation_type == 'delete':
            self.pinecone_index.delete(ids=[str(change['documentKey']['_id'])])

    def watch_changes(self):
        """Open a change stream cursor to listen for changes in the MongoDB collection."""
        cursor = self.collection.watch(full_document='updateLookup')
        print("Change stream is now open.")
        for change in cursor:
            self.handle_change(change)

    def start(self):
        """Start the MongoDB change listener in a separate thread."""
        thread = threading.Thread(target=self.watch_changes, daemon=True)
        thread.start()
        print("MongoDB listener thread started.")

    def get_similar_results(self, query, similar_result=3):
        """Query Pinecone for similar results and retrieve documents from MongoDB."""
        embedding = self.encode_text(query)

        # Query Pinecone
        result = self.pinecone_index.query(
            vector=embedding,
            top_k=similar_result,
        )

        # Retrieve matching documents from MongoDB
        matched_documents = []
        for match in result["matches"]:
            doc_id = match["id"]
            document = self.collection.find_one({"_id": ObjectId(doc_id)})
            if document:
                matched_documents.append(document)

        return matched_documents

    def format_combined_information(self, matched_documents):
        """Combine and format information from matched documents."""
        combined_information = ""
        for document in matched_documents:
            title = document.get("title", "N/A")
            fullplot = document.get("fullplot", "N/A")
            combined_information += f"Title: {title}, Fullplot: {fullplot}\n"
        return combined_information
