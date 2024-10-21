from flask import Flask, request, render_template, redirect, url_for, session
from collections import defaultdict
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from ytmusicapi import YTMusic
from fuzzywuzzy import fuzz
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Flask app initialization
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")  # Use the secret key from .env

# Spotify credentials
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")

scope = "playlist-read-private"
sp_oauth = SpotifyOAuth(client_id=SPOTIPY_CLIENT_ID,
                        client_secret=SPOTIPY_CLIENT_SECRET,
                        redirect_uri=SPOTIPY_REDIRECT_URI,
                        scope=scope)

# YouTube Music API initialization
ytmusic = YTMusic()

# Function to get tracks from a Spotify playlist
def get_spotify_tracks(playlist_id, sp):
    results = sp.playlist_tracks(playlist_id)
    tracks = results.get('items', [])

    song_list = []
    if not tracks:
        return song_list

    for item in tracks:
        track = item.get('track')
        if track is None:
            continue
        song_name = track.get('name', 'Unknown Song')
        artist_name = track['artists'][0].get('name', 'Unknown Artist') if track.get('artists') else 'Unknown Artist'
        song_list.append({'name': song_name, 'artist': artist_name, 'id': track['id']})

    return song_list

# Function to get song recommendations from YouTube Music
def get_youtube_music_recommendations(song_name, artist_name, track_id):
    # Log search query for debugging
    print(f"Searching YouTube Music for: {song_name} {artist_name}")

    # Search YouTube Music for songs matching the query
    search_results = ytmusic.search(f'{song_name} {artist_name}', filter='songs')
    print(f"Search results: {search_results}")  # Log the search results

    recommendations = []

    if search_results:
        for result in search_results[:10]:
            # Handle missing artist information
            artist = result.get('artists', [{'name': 'Unknown Artist'}])[0]['name']

            # Skip exact matches using fuzzy matching
            if fuzz.ratio(result['title'].lower(), song_name.lower()) > 90 and fuzz.ratio(artist.lower(), artist_name.lower()) > 90:
                continue  # Skip exact matches

            # Handle missing thumbnail information
            thumbnail = result.get('thumbnails', [{'url': None}])[0]['url']

            # Construct Spotify URL using the provided track_id
            spotify_url = f"https://open.spotify.com/track/{track_id}"
            print(f"Spotify URL: {spotify_url}")  # Log Spotify URL for debugging

            # Add recommendation to the list
            recommendations.append({
                'title': result['title'],
                'artist': artist,
                'album': result.get('album', {}).get('name', 'N/A'),  # Handle missing album info
                'thumbnail': thumbnail,
                'views': result.get('views', '0'),  # Default to 0 if views are not provided
                'spotify_url': spotify_url  # Include Spotify URL in recommendations
            })
    else:
        print("No search results found.")

    return recommendations


# Function to filter out duplicates and get top recommendations
def filter_and_get_top_recommendations(spotify_tracks, all_recommendations):
    # Dictionary to store recommendation counts
    recommendation_count = defaultdict(int)
    playlist_songs = set(f"{track['name'].lower()} by {track['artist'].lower()}" for track in spotify_tracks)

    # Count occurrences of recommendations, excluding songs already in the playlist
    for rec in all_recommendations:
        rec_key = f"{rec['title'].lower()} by {rec['artist'].lower()}"
        if rec_key not in playlist_songs:
            recommendation_count[rec_key] += 1

    # Get top 10 recommendations based on count
    top_recommendations = sorted(recommendation_count.items(), key=lambda x: x[1], reverse=True)[:10]

    # Prepare the final list of recommendations
    final_recommendations = []
    for rec_key, _ in top_recommendations:
        song_title, song_artist = rec_key.split(" by ")
        rec_info = next((rec for rec in all_recommendations if rec['title'].lower() == song_title and rec['artist'].lower() == song_artist), None)
        if rec_info:
            final_recommendations.append(rec_info)

    return final_recommendations

# Home route
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        playlist_link = request.form.get('playlist_link')

        if playlist_link:
            try:
                # Store the playlist link in the session
                session['playlist_link'] = playlist_link

                # Get Spotify authorization URL
                auth_url = sp_oauth.get_authorize_url()
                return redirect(auth_url)

            except Exception as e:
                return render_template('index.html', error=f"Error: {str(e)}")

    return render_template('index.html')
@app.route('/callback', methods=['GET', 'POST'])
def callback():
    try:
        # Get the playlist link from the session
        playlist_link = session.get('playlist_link')
        if not playlist_link:
            return render_template('index.html', error="Playlist link not found in session.")

        # Retrieve the authorization code and get the access token
        code = request.args.get('code')
        if not code:
            return render_template('index.html', error="Authorization code not found.")

        # Get the access token using the authorization code
        token_info = sp_oauth.get_access_token(code)
        if not token_info:
            return render_template('index.html', error="Could not retrieve access token.")

        access_token = token_info['access_token']
        sp = spotipy.Spotify(auth=access_token)  # Use the access token directly

        # Use the Spotify client to fetch tracks from the Spotify playlist
        SPOTIFY_PLAYLIST_ID = playlist_link.split("/")[-1].split("?")[0]
        spotify_tracks = get_spotify_tracks(SPOTIFY_PLAYLIST_ID, sp)

        if not spotify_tracks:
            return render_template('index.html', error="No tracks found in the playlist.")
        else:
            all_recommendations = []

            # Get YouTube Music recommendations for each song from the Spotify playlist
            for track in spotify_tracks:
                song_name = track['name']
                artist_name = track['artist']
                track_id = track['id']  # Extract the track ID from Spotify tracks
                youtube_recommendations = get_youtube_music_recommendations(song_name, artist_name, track_id)
                all_recommendations.extend(youtube_recommendations)

            # Filter and get top 10 unique recommendations
            top_recommendations = filter_and_get_top_recommendations(spotify_tracks, all_recommendations)

            # Display only the top 10 recommendations
            return render_template('index.html', recommendations=top_recommendations)

    except Exception as e:
        return render_template('index.html', error=f"Error: {str(e)}")

# Run the app
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Use the PORT environment variable if available, else default to 5000
    app.run(host='0.0.0.0', port=port, debug=True)
