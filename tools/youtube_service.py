import os
import json
from typing import List, Dict, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging
import psycopg2
import psycopg2.extras

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class YouTubeService:
    """Service class to interact with YouTube Data API v3"""
    
    def __init__(self, api_key: str = None):
        """
        Initialize YouTube service with API key
        
        Args:
            api_key: YouTube Data API v3 key. If None, will try to get from environment
        """
        # api_key="AIzaSyAYCO5rrPanqvpoH7IZ-Cob0DxzFjtMDUk" 
        api_key="AIzaSyAZudWt-i92ArrTQfdj_SA6Tmd_cUAKwlY"
        self.api_key = api_key or os.getenv('YOUTUBE_API_KEY')
        print(f"Initializing YouTube service with API key: { os.getenv('YOUTUBE_API_KEY')}")
        if not self.api_key:
            raise ValueError("YouTube API key is required. Set YOUTUBE_API_KEY environment variable or pass api_key parameter.")
        
        self.youtube = build('youtube', 'v3', developerKey=self.api_key)
        self.channel_id = "UCqJkAAmi4QKCPCF62r_-BhQ"
        self.channel_name = "India Food Network"
        self.channel_handle = "@Indiafoodnetwork"
    
    def get_channel_id(self, channel_handle: str = None) -> Optional[str]:
        """
        Get channel ID from channel handle
        
        Args:
            channel_handle: Channel handle (e.g., "@Indiafoodnetwork")
        
        Returns:
            Channel ID if found, None otherwise
        """
        handle = channel_handle or self.channel_handle
        
        try:
            # Remove @ if present
            handle = handle.lstrip('@')
            
            # Search for channel by handle
            search_response = self.youtube.search().list(
                q=handle,
                type='channel',
                part='id,snippet',
                maxResults=2
            ).execute()
            
            # Look for exact match
            for item in search_response.get('items', []):
                if item['snippet']['title'].lower() == self.channel_name.lower():
                    self.channel_id = item['id']['channelId']
                    logger.info(f"Found channel ID: {self.channel_id}")
                    return self.channel_id
            
            # If no exact match, try the first result
            if search_response.get('items'):
                self.channel_id = search_response['items'][0]['id']['channelId']
                logger.info(f"Using first search result channel ID: {self.channel_id}")
                return self.channel_id
                
        except HttpError as e:
            logger.error(f"Error getting channel ID: {e}")
            return None
    
    def search_videos(self, 
                     query: str = "", 
                     max_results: int = 10, 
                     order: str = "relevance",
                     published_after: str = None) -> List[Dict]:
        """
        Search for videos in the India Food Network channel
        
        Args:
            query: Search query (e.g., "chicken curry", "biryani")
            max_results: Maximum number of results to return (1-50)
            order: Sort order ('relevance', 'date', 'rating', 'viewCount', 'title')
            published_after: RFC 3339 formatted date-time (e.g., "2024-01-01T00:00:00Z")
        
        Returns:
            List of video dictionaries with metadata
        """
        if not self.channel_id:
            if not self.get_channel_id():
                logger.error("Could not retrieve channel ID")
                return []
        
        try:
            search_params = {
                'q': query,
                'channelId': self.channel_id,
                'type': 'video',
                'part': 'id,snippet',
                'maxResults': min(max_results, 50),  # API limit
                'order': order
            }
            
            if published_after:
                search_params['publishedAfter'] = published_after
            
            search_response = self.youtube.search().list(**search_params).execute()
            
            videos = []
            for item in search_response.get('items', []):
                video_info = {
                    'video_id': item['id']['videoId'],
                    'title': item['snippet']['title'],
                    'description': item['snippet']['description'],
                    'published_at': item['snippet']['publishedAt'],
                    'channel_title': item['snippet']['channelTitle'],
                    'thumbnail_url': item['snippet']['thumbnails']['high']['url'],
                    'video_url': f"https://www.youtube.com/watch?v={item['id']['videoId']}"
                }
                videos.append(video_info)
            
            logger.info(f"Found {len(videos)} videos for query: '{query}'")
            return videos
            
        except HttpError as e:
            logger.error(f"Error searching videos: {e}")
            return []
    
    def parse_ingredients(self, description: str) -> List[str]:
        """
        Parse ingredients from a video description.
        Looks for an 'Ingredients' section and extracts lines until
        the next section header or end of description.

        Args:
            description: Full video description text

        Returns:
            List of ingredient strings
        """
        ingredients = []
        lines = description.split("\n")
        in_ingredients_section = False

        for line in lines:
            stripped = line.strip()

            # Detect start of ingredients section
            if stripped.lower().startswith("ingredient"):
                in_ingredients_section = True
                continue  # Skip the header line itself

            if in_ingredients_section:
                # Stop if we hit a new section header (e.g., "Method:", "Instructions:", empty + caps)
                if not stripped:
                    continue  # Skip blank lines inside the section
                if stripped.endswith(":") and len(stripped.split()) <= 3:
                    break  # New section found, stop collecting
                ingredients.append(stripped)

        return ingredients
    
    def get_uploads_playlist_id(self):
        response = self.youtube.channels().list(
            part="contentDetails",
            id=self.channel_id
        ).execute()

        return response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    
    def save_to_postgres(self, videos: List[Dict]) -> int:
        """
        Insert video data into the flask_yt_details PostgreSQL table.
        Skips duplicates based on url (ON CONFLICT DO NOTHING).

        Args:
            videos: List of video dicts with title, description, url, ingredients

        Returns:
            Number of rows inserted
        """
        DB_URL = "postgres://postgres:gMAJTwTSA9eeuQ56TfxeogJWOaekm5q4WbkZ02sFB8tHIynd3CGUsMgZvXeo9ONM@72.62.197.102:5898/recipe_finder"

        inserted = 0
        try:
            conn = psycopg2.connect(DB_URL)
            cursor = conn.cursor()

            # for video in videos:
            #     cursor.execute(
            #         """
            #         INSERT INTO flask_yt_details (title, description, url, ingredients)
            #         VALUES (%s, %s, %s, %s)
            #         """,
            #         (
            #             video.get("title"),
            #             video.get("description"),
            #             video.get("youtube_url"),
            #             json.dumps(video.get("ingredients", []))
            #         )
            #     )
            
            for video in videos:
                cursor.execute(
                    """
                    INSERT INTO flask_yt_details (title, description, url, ingredients, published_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        video.get("title"),
                        video.get("description"),
                        video.get("youtube_url"),
                        json.dumps(video.get("ingredients", [])),
                        video.get("published_date")
                    )
                )
                if cursor.rowcount > 0:
                    inserted += 1

            conn.commit()
            cursor.close()
            conn.close()
            logger.info(f"Inserted {inserted} new videos into flask_yt_details")

        except Exception as e:
            logger.error(f"PostgreSQL error: {e}")
            raise

        return inserted
    
    def fetch_all_channel_videos(self):
        playlist_id = self.get_uploads_playlist_id()

        videos = []
        next_page_token = None

        while True:
            response = self.youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            for item in response.get("items", []):
                video_id = item["snippet"]["resourceId"]["videoId"]

                videos.append({
                    "video_id": video_id,
                    "title": item["snippet"]["title"],
                    "description": item["snippet"]["description"],
                    "published_at": item["snippet"]["publishedAt"],
                    "thumbnail_url": item["snippet"]["thumbnails"]["high"]["url"],
                    "youtube_url": f"https://www.youtube.com/watch?v={video_id}"
                })

            next_page_token = response.get("nextPageToken")

            if not next_page_token:
                break

        return videos

    # def fetch_all_channel_videos_with_details(self, max_results: int = 50, output_file: str = "channel_videos.json") -> List[Dict]:
    #     """
    #     Fetch all videos from the channel with title, full description,
    #     ingredients (parsed from full description), and YouTube URL.
        
    #     Uses get_video_details() after search to retrieve the FULL description,
    #     since search snippets are truncated and don't contain ingredients.

    #     Args:
    #         max_results: Number of videos to fetch (max 50 per API call)
    #         output_file: JSON file name to save data

    #     Returns:
    #         List of video data
    #     """
    #     try:
    #         # Step 1: Search to get video IDs and basic info
    #         # videos = self.fetch_all_channel_videos(max_results=max_results)
    #         videos = self.fetch_all_channel_videos()


    #         if not videos:
    #             logger.warning("No videos returned from search.")
    #             return []

    #         # Step 2: Extract video IDs and fetch FULL details (full description)
    #         video_ids = [v["video_id"] for v in videos]
    #         detailed_videos = self.get_video_details(video_ids)

    #         # Build a lookup map: video_id -> full details
    #         details_map = {v["video_id"]: v for v in detailed_videos}

    #         final_data = []

    #         for video in videos:
    #             video_id = video["video_id"]

    #             # Use full details if available, fallback to search snippet
    #             full_detail = details_map.get(video_id, {})
    #             full_description = full_detail.get("description") or video.get("description", "")

    #             # Parse ingredients from the complete description
    #             ingredients = self.parse_ingredients(full_description)

    #             video_data = {
    #                 "title": video.get("title"),
    #                 "description": full_description,
    #                 "ingredients": ingredients,
    #                 "youtube_url": video.get("youtube_url")
    #             }

    #             final_data.append(video_data)

    #         # Step 3: Save to JSON
    #         with open(output_file, "w", encoding="utf-8") as f:
    #             json.dump(final_data, f, indent=2, ensure_ascii=False)

    #         logger.info(f"Saved {len(final_data)} videos to {output_file}")

    #         return final_data

    #     except Exception as e:
    #         logger.error(f"Error fetching channel videos: {e}")
    #         return []
    
    def fetch_all_channel_videos_with_details(self) -> List[Dict]:
        try:
            # Step 1: Fetch all videos from uploads playlist
            videos = self.fetch_all_channel_videos()   # ← no arguments

            logger.info(f"Fetched {len(videos)} videos from playlist")  # ← add this to verify

            if not videos:
                logger.warning("No videos returned from channel.")
                return []

            # Step 2: Fetch FULL details in batches of 50
            video_ids = [v["video_id"] for v in videos]
            detailed_videos = self.get_video_details(video_ids)
            details_map = {v["video_id"]: v for v in detailed_videos}

            final_data = []
            for video in videos:
                video_id = video["video_id"]
                full_detail = details_map.get(video_id, {})
                full_description = full_detail.get("description") or video.get("description", "")
                ingredients = self.parse_ingredients(full_description)

                # final_data.append({
                #     "title": video.get("title"),
                #     "description": full_description,
                #     "ingredients": ingredients,
                #     "youtube_url": video.get("youtube_url")  # ← correct key
                # })
                
                final_data.append({
                    "title": video.get("title"),
                    "description": full_description,
                    "ingredients": ingredients,
                    "youtube_url": video.get("youtube_url"),
                    "published_date": full_detail.get("published_at") or video.get("published_at")
                })

            # Step 3: Push to PostgreSQL
            inserted = self.save_to_postgres(final_data)
            logger.info(f"Done. {inserted} new rows inserted out of {len(final_data)} videos.")

            return final_data

        except Exception as e:
            logger.error(f"Error fetching channel videos: {e}")
            raise   # ← change from `return []` to `raise` so you can SEE the actual error
    
    def get_video_details(self, video_ids: List[str]) -> List[Dict]:
        """
        Get detailed information about specific videos
        
        Args:
            video_ids: List of video IDs
        
        Returns:
            List of detailed video information
        """
        if not video_ids:
            return []
        
        try:
            # YouTube API allows up to 50 video IDs per request
            video_details = []
            
            for i in range(0, len(video_ids), 50):
                batch_ids = video_ids[i:i+50]
                
                videos_response = self.youtube.videos().list(
                    part='snippet,statistics,contentDetails',
                    id=','.join(batch_ids)
                ).execute()
                
                for item in videos_response.get('items', []):
                    video_info = {
                        'video_id': item['id'],
                        'title': item['snippet']['title'],
                        'description': item['snippet']['description'],
                        'published_at': item['snippet']['publishedAt'],
                        'channel_title': item['snippet']['channelTitle'],
                        'duration': item['contentDetails']['duration'],
                        'view_count': item['statistics'].get('viewCount', 0),
                        'like_count': item['statistics'].get('likeCount', 0),
                        'comment_count': item['statistics'].get('commentCount', 0),
                        'thumbnail_url': item['snippet']['thumbnails']['high']['url'],
                        'video_url': f"https://www.youtube.com/watch?v={item['id']}"
                    }
                    video_details.append(video_info)
            
            return video_details
            
        except HttpError as e:
            logger.error(f"Error getting video details: {e}")
            return []
    
    def get_recent_videos(self, max_results: int = 10) -> List[Dict]:
        """
        Get recent videos from the India Food Network channel
        
        Args:
            max_results: Maximum number of results to return
        
        Returns:
            List of recent video dictionaries
        """
        return self.search_videos(
            query="",  # Empty query to get all videos
            max_results=max_results,
            order="date"
        )
    
    def search_recipe_videos(self, recipe_name: str, max_results: int = 5) -> List[Dict]:
        """
        Search for specific recipe videos
        
        Args:
            recipe_name: Name of the recipe (e.g., "butter chicken", "biryani")
            max_results: Maximum number of results to return
        
        Returns:
            List of recipe video dictionaries
        """
        return self.search_videos(
            query=f"{recipe_name} recipe",
            max_results=max_results,
            order="relevance"
        )
    
    def export_to_json(self, videos: List[Dict], filename: str = "youtube_videos.json"):
        """
        Export video data to JSON file
        
        Args:
            videos: List of video dictionaries
            filename: Output filename
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(videos, f, indent=2, ensure_ascii=False)
            logger.info(f"Exported {len(videos)} videos to {filename}")
        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")


    
# Example usage and testing functions
def main():
    """Example usage of the YouTubeService"""
    
    # Initialize service (make sure to set YOUTUBE_API_KEY environment variable)
    try:
        youtube_service = YouTubeService()
    except ValueError as e:
        print(f"Error: {e}")
        print("Please set your YouTube API key in the YOUTUBE_API_KEY environment variable")
        return
    
    # Search for specific recipe videos
    print("Searching for chicken curry recipes...")
    chicken_videos = youtube_service.search_recipe_videos("chicken curry", max_results=5)
    
    for video in chicken_videos:
        print(f"Title: {video['title']}")
        print(f"URL: {video['video_url']}")
        print(f"Published: {video['published_at']}")
        print("-" * 50)
    
    # Get recent videos
    print("\nGetting recent videos...")
    recent_videos = youtube_service.get_recent_videos(max_results=3)
    
    for video in recent_videos:
        print(f"Title: {video['title']}")
        print(f"URL: {video['video_url']}")
        print(f"Published: {video['published_at']}")
        print("-" * 50)
    
    # Get detailed information for first video
    if recent_videos:
        video_ids = [recent_videos[0]['video_id']]
        detailed_info = youtube_service.get_video_details(video_ids)
        
        if detailed_info:
            video = detailed_info[0]
            print(f"\nDetailed info for: {video['title']}")
            print(f"Duration: {video['duration']}")
            print(f"Views: {video['view_count']}")
            print(f"Likes: {video['like_count']}")
    
    # Export all videos to JSON
    all_videos = chicken_videos + recent_videos
    youtube_service.export_to_json(all_videos, "india_food_network_videos.json")


if __name__ == "__main__":
    main()