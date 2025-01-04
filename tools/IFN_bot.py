import os
from langchain_google_genai import ChatGoogleGenerativeAI
from tools.vectorstore import VectorStore

class IFNBot:
    def __init__(self, mongo_uri, mongo_db, mongo_collection, pinecone_api_key, pinecone_index_name, embedding_model_name='sentence-transformers/all-MiniLM-L6-v2', pinecone_env='us-east-1-gcp-free'):
        # Initialize the VectorStore (MongoDB + Pinecone)
        self.vector_store = VectorStore(
            mongo_uri=mongo_uri,
            mongo_db=mongo_db,
            mongo_collection=mongo_collection,
            pinecone_api_key=pinecone_api_key,
            pinecone_index_name=pinecone_index_name,
            embedding_model_name=embedding_model_name,
            pinecone_env=pinecone_env
        )

        # Load the model
        self.llm_model = self.load_model("gemini-pro")

    def load_model(self, model_name):
        """Load the LLM model based on the model name"""
        if model_name == "gemini-pro":
            llm = ChatGoogleGenerativeAI(model="gemini-pro")
        else:
            llm = ChatGoogleGenerativeAI(model="gemini-pro-vision")
        return llm

    def process_query(self, query):
        """Process the query, fetch relevant data from VectorStore, and get LLM response"""
        # Step 1: Get similar content from VectorStore
        results = self.vector_store.get_similar_results(query)

        # Step 2: Format the combined information
        combined_information = self.vector_store.format_combined_information(results)

        # Step 3: Create a prompt with the relevant content
        prompt = f"Here is some relevant information:\n{combined_information}\n\nBased on this, please answer the user's query: {query}"

        # Step 4: Get the response from the LLM
        response = self.llm_model.chat(prompt)
        return response

    def generate_query_from_ingredients(self, ingredients):
        """Generate a query for dishes based on the detected ingredients"""
        query = f"What dishes can I make with {', '.join(ingredients)}?"
        return query