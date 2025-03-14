"""References: 
https://wiki.sponsor.ajay.app/w/API_Docs
https://sponsorblockpy.readthedocs.io/en/latest/
https://stackoverflow.com/questions/67233609/extract-audio-from-youtube-video
https://kkroening.github.io/ffmpeg-python/index.html
https://ffmpeg.org/ffmpeg-filters.html#atrim
"""

import os
import sys

sys.path.append('c:\\Users\\abarc\\Desktop\\andrei\\projects\\Python\\local\\sponsorblock.py')

import ffmpeg
import asyncio
from googleapiclient.discovery import build, Resource
import assemblyai as aai
from google import genai
import sponsorblock as sb
from pytubefix import YouTube
from dateutil.parser import isoparse
from typing import List, Tuple, Union
from datetime import datetime, timezone
import yt_dlp


def get_stream_url(video_url):
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'cookiefile': 'youtube_cookies.txt',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        return info['url']
    

def get_or_create_event_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError as ex:
        if "There is no current event loop in thread" in str(ex):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
        else:
            raise ex


def time_ago(iso_timestamp):
    # Convert ISO 8601 string to datetime object
    published_time = isoparse(iso_timestamp).replace(tzinfo=timezone.utc)
    
    # Get current time in UTC
    now = datetime.now(timezone.utc)
    
    # Calculate time difference
    diff = now - published_time
    
    # Convert to human-readable format
    if diff.days > 0:
        return f"{diff.days} days ago"
    elif diff.seconds >= 3600:
        return f"{diff.seconds // 3600} hours ago"
    elif diff.seconds >= 60:
        return f"{diff.seconds // 60} minutes ago"
    else:
        return "Just now"


def get_sponsorship_segments(sbclient: sb.Client, link: str) -> List[Tuple[float, float]]:
    """Returns a list of tuples of start and stop times of sponsorship segments in a YouTube video extracted using Sponsorblock API.

    Args:
      link (str):
        URL link to a YouTube video.
    
    Returns:
      sponsorships_timeframes (List[Tuple[float, float]]):
        list of tuples, where each tuple is the start and stop time for a particular sponsorship segment.
    """

    # get the sponsorship(s) timeframes in seconds.
    try:
        segments = sbclient.get_skip_segments(link)
        # each item is a tuple of sponsorship start time and stop time in seconds.
        # keep only sponsorship segments the sponsorblock community flagged as skippable and get the times of those segments.
        sponsorships_timeframes = list(map(lambda sponsor_segment: sponsor_segment.data['segment'], 
                filter(lambda segment: segment.action_type == 'skip', segments)))
        # Sometimes the same segment is listed more than once but with slight time offsets,
        #  filter out these duplicates, keeping only unique segments, 
        #  merging a segment if one segment is part of a longer segment.
        tolerance = 2.0 # upper limit for the gap (sec) between segments' start or stop times.

        def get_unique_sponsorships(timeframes_list, tolerance):
            for i in range(0, len(timeframes_list)-1):
                timeframe1 = timeframes_list[i] # tuple of (start_time, stop_time).
                timeframe2 = timeframes_list[i+1]
                # check if two timeframes correspond to the same sponsorship.
                if abs(timeframe1[0] - timeframe2[0]) < tolerance:
                    # timegap between the start times is less than 'tolerance' seconds.
                    # segments correspond to the same sponsorship promotion, but one may have an incorrect shorter timeframe.
                    # keep the longer stop time and combine the segments into one (start time unchanged as it is the same).
                        timeframes_list[i][1] = max(timeframe1[1], timeframe2[1]) # replace (i)'th tuple's stop time with the largest of the two.
                        del timeframes_list[i+1] # delete (i+1)'st tuple.
                        return True
            return False

        while get_unique_sponsorships(sponsorships_timeframes, tolerance): pass

    except sb.errors.NotFoundException:
        print(f"No sponsorship segments were found for the video {link}")
        sponsorships_timeframes = []

    return sponsorships_timeframes


def get_sponsorship_audio(link: str, sponsorship_timeframe: Tuple[float, float]) -> str:
    """Returns the temporary filepath of the sponsorship audio from the YouTube video, specified by the timeframe using Pytube and ffmpeg.

    Args:
      link (str):
        URL link to a YouTube video.
      sponsorship_timeframe (Tuple[float, float]):
        tuple of the start and stop times of the sponsorship segment.
    
    Returns:
      temp_filename (string):
        the temporarily saved path to wav file containing the sponsorship segment.
    """

    # yt = YouTube(link) # pytube
    # stream_url1 = yt.streams.all()[0].url  # Get the URL of the video stream.
    # Example usage
    stream_url2 = get_stream_url(link)

    # Probe the audio streams (use it in case you need information like sample rate):
    #probe = ffmpeg.probe(stream_url)
    #audio_streams = next((stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), None)
    #sample_rate = audio_streams['sample_rate']

    # Read audio into memory buffer.
    # Get the audio using stdout pipe of ffmpeg sub-process.
    # The audio is transcoded to PCM codec in WAC container.
    audio, err = (
        ffmpeg
        .input(stream_url2)
        # ffmpeg 'atrim' filter extracting the sponsorship segment of audio and keeping it in memory.
        .audio.filter("atrim", start=sponsorship_timeframe[0], end=sponsorship_timeframe[1])
        .output("pipe:", format='wav', acodec='pcm_s16le')  # Select WAV output format, and pcm_s16le auidio codec. My add ar=sample_rate
        .run(capture_stdout=True))

    if not err:
        temp_filename = 'temp_audio.wav'
        # Write the audio buffer to file temporarily
        with open(temp_filename, 'wb') as f:
            f.write(audio)

        return temp_filename
    

def get_sponsorships_from_video(sbclient: sb.Client, gclient: genai.Client, transcriber: aai.Transcriber, yt_link: str) -> str:
    sponsorships_timeframes = get_sponsorship_segments(sbclient, yt_link)

    # extract the audio from the sponsorship segments.
    if sponsorships_timeframes:
        sponsorships = []
        # process each sponsorship segment in this video.
        for sponsorship_timeframe in sponsorships_timeframes:
            audio_filepath = get_sponsorship_audio(yt_link, sponsorship_timeframe)

            # transcribe sponsorship.
            transcript = transcriber.transcribe(audio_filepath)

            if transcript.status == aai.TranscriptStatus.error:
                print(f"Transcription failed: {transcript.error}")
                exit(1)
            
            txt = transcript.text

            # get the sponsorship gist using PaLM.

            # define the user prompt message.
            prompt = "Summarise what product the following advertisement from a YouTube video is about and let the user know if there are any promotions like discounts on mentioned products: " + txt
            # create a chatbot and complete the prompt request.
            response = gclient.models.generate_content(model="gemini-2.0-flash", contents=prompt).text
            sponsorships.append(response)
            # remove the temporarily created audio file of the sponsorship segment.
            os.remove('temp_audio.wav')

        return sponsorships
    

def setup() -> Union[sb.Client, genai.Client, aai.Transcriber, Resource]:
    # initialise sponsorblock client.
    sbclient = sb.Client()

     # Ensure an event loop exists before initializing the client
    get_or_create_event_loop()

    # sign up at https://aistudio.google.com/app/apikey to get API key.
    # create a PALM_API_KEY environment variable.
    gclient = genai.Client(api_key=os.environ['PALM_API_KEY'])

    # sign up at assemblyai.com to get API key.
    # create a ASSEMBLYAI_API_KEY environment variable.
    aai.settings.api_key = os.environ['ASSEMBLYAI_API_KEY']
    transcriber = aai.Transcriber()

    # set up connectivity to YouTube API, follow tutorial https://www.youtube.com/watch?v=TIZRskDMyA4.
    yt = build(
        'youtube', 
        'v3',
        developerKey=os.environ['YOUTUBE_API_KEY']
    )
    return sbclient, gclient, transcriber, yt


def by_channel(channel_handle: str, num_videos: int = 3) -> List[dict]:
    """Returns the sponsorships integrated in the YouTube videos of channel specified by its handle along with the number of most recent videos to check.

    Returns:
        List[
            dict{
                'url': YouTube video URL.
                'sponsorships': List[str]
                'time_ago': str
            }
        ]
    """
    sbclient, gclient, transcriber, yt = setup()

    # Get the 'num_videos' amount of most recent videos for the channel specified by its handle.
    channel_request = yt.channels().list(
        part="snippet,contentDetails,statistics",
        forHandle=channel_handle
    )

    channel_response = channel_request.execute()

    if not channel_response.get('items'):
        print(f"ERROR: No such channel handle.")
        return []
    uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # fetch the 'num_videos' amount of most recent videos from the uploads playlist.
    playlist_request = yt.playlistItems().list(
        part="snippet",
        playlistId=uploads_playlist_id,
        maxResults=num_videos
    )
    try:
        playlist_response = playlist_request.execute()
    except Exception:
        print(f"ERROR: Number of videos specified is less than 1.")
        return []

    sponsorss = list()
    # loop through the most recent videos.
    for item in playlist_response["items"]:
        video_id = item["snippet"]["resourceId"]["videoId"]
        title = item["snippet"]["title"]
        published_at = item["snippet"]["publishedAt"]  # time of publishing.
        # get sponsorships.
        sponsorships = get_sponsorships_from_video(sbclient, gclient, transcriber, f"https://www.youtube.com/watch?v={video_id}")
        sponsors = dict()
        sponsors['url'] = f"https://www.youtube.com/watch?v={video_id}"
        if sponsorships:
            sponsors['sponsorships'] = list()
            for sponsorship in sponsorships:
                sponsors['sponsorships'].append(sponsorship)
        sponsors['time_ago'] = time_ago(published_at)
        sponsorss.append(sponsors)
    
    return sponsorss


def by_video(yt_link: str) -> dict:
    """Returns the sponsorships integrated in the YouTube video specified by the link in the argument.

    Returns:
        dict{
            'url': YouTube video URL.
            'sponsorships': List[str]
        }
    """

    sbclient, gclient, transcriber, _ = setup()
    # get sponsorships.
    sponsorships = get_sponsorships_from_video(sbclient, gclient, transcriber, yt_link)
    sponsors = dict()
    sponsors['url'] = yt_link
    if sponsorships:
        sponsors['sponsorships'] = list()
        for sponsorship in sponsorships:
            sponsors['sponsorships'].append(sponsorship)

    return sponsors


if __name__ == "__main__":
    b = by_video("https://www.youtube.com/watch?v=2e31eEkII8U")
    # b = by_channel("Insider", -1)
    a=1

    

    

    
            