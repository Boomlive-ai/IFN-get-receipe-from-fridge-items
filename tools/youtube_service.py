import os
import json
from typing import List, Dict, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

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
        api_key="AIzaSyCf8FFyjpQWPMv79Xu_slqY3fnKUmb9-qg"
        self.api_key = api_key or os.getenv('YOUTUBE_API_KEY')
        if not self.api_key:
            raise ValueError("YouTube API key is required. Set YOUTUBE_API_KEY environment variable or pass api_key parameter.")
        
        self.youtube = build('youtube', 'v3', developerKey=self.api_key)
        self.channel_id = None
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
                maxResults=10
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