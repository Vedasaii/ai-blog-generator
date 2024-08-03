from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
import json
import pytube.exceptions
from pytube import YouTube
import os
import yt_dlp as youtube_dl
import assemblyai as aai
import google.generativeai as genai
import logging
from .models import BlogPost

ASSEMBLYAI_API_KEY = "41a45fc8b9754999a57db436da7cb42c"


logger = logging.getLogger(__name__)
@csrf_exempt
def generate_blog(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            yt_link = data.get('link')
            if not yt_link:
                return JsonResponse({'error': 'YouTube link not provided'}, status=400)
            logger.info(f"YouTube Link: {yt_link}")
        except (KeyError, json.JSONDecodeError) as e:
            logger.error(f"Error decoding JSON: {e}")
            return JsonResponse({'error': 'Invalid data sent'}, status=400)

        if not validate_youtube_url(yt_link):
            logger.error("Invalid YouTube URL")
            return JsonResponse({'error': 'Invalid YouTube URL'}, status=400)

        try:
            title = yt_title(yt_link)
            logger.info(f"YouTube Title: {title}")
        except Exception as e:
            logger.error(f"Error getting YouTube title: {e}")
            return JsonResponse({'error': f'Failed to get YouTube title: {str(e)}'}, status=500)

        try:
            transcription = get_transcription(yt_link)
            logger.info(f"Transcription: {transcription}")
            if not transcription:
                return JsonResponse({'error': "Failed to get transcription"}, status=500)
        except Exception as e:
            logger.error(f"Error getting transcription: {e}")
            return JsonResponse({'error': f'Failed to get transcription: {str(e)}'}, status=500)

        try:
            blog_content = generate_blog_from_transcription(transcription)
            logger.info(f"Blog Content: {blog_content}")
            if not blog_content:
                return JsonResponse({'error': "Failed to generate blog article"}, status=500)
        except Exception as e:
            logger.error(f"Error generating blog article: {e}")
            return JsonResponse({'error': f'Failed to generate blog article: {str(e)}'}, status=500)

        new_blog_article = BlogPost.objects.create(
            user = request.user,
            youtube_title = title,
            youtube_link = yt_link,
            generated_content = blog_content
        )
        new_blog_article.save()
        
        return JsonResponse({'content': blog_content})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)

def get_transcription(link):
    
    audio_file = download_audio(link)
    aai.settings.api_key = ASSEMBLYAI_API_KEY

    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_file)
    # print(transcript.text)
    return transcript.text

  

def generate_blog_from_transcription(transcription):
    genai.configure(api_key= "AIzaSyDUDJ9SSWvFDaizCma1HYVmooPFmi2utKM")
    prompt = f"Based on the following transcript from a YouTube video, write a comprehensive blog article. Write it based on the transcript, but do not make it look like a YouTube video and don't give any defined spaces to input something; make it a proper blog article:\n\n{transcription}\n\nArticle:"
    print(transcription)
    try:
        generation_config = {
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        }
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=generation_config,
            # safety_settings = Adjust safety settings
            # See https://ai.google.dev/gemini-api/docs/safety-settings
        )

        chat_session = model.start_chat(
            history=[]
        )

        response = chat_session.send_message(prompt)

        logger.debug(f"Gemini response: {response.text}")  # Debug statement to log the response
        
        # Extract and return the generated content
        generated_content = response.text
        return generated_content
    
    except Exception as e:
        logger.error(f"Error in generation: {e}", exc_info=True)
        raise

def validate_youtube_url(url):
    """
    Validate if the provided URL is a valid YouTube URL.
    """
    return 'youtube.com/watch?v=' in url or 'youtu.be/' in url

def yt_title(link):
    yt = YouTube(link)
    title = yt.title
    return title


def download_audio(link):
    try:
        # Options to download only audio and convert to MP3
        ydl_opts = {
            'format': 'bestaudio/best',  # Download the best audio quality
            'outtmpl': os.path.join(settings.MEDIA_ROOT, '%(title)s.%(ext)s'),  # Output path
            'postprocessors': [{  # Post-processing to convert audio to MP3
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'ffmpeg_location': 'C:/ffmpeg/bin/',  # Path to ffmpeg executable if not in PATH
            'quiet': True,  # Suppress output
        }
        
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(link, download=True)  # Download the audio
            
            # Prepare and rename the file
            file_name = ydl.prepare_filename(info_dict)  # Prepare file name
            print(f"Original file name: {file_name}")  # Debug statement
            
            base, ext = os.path.splitext(file_name)
            new_file = base + '.mp3'  # Rename to MP3 extension
            
            print(f"Renaming file to: {new_file}")  # Debug statement
            if os.path.exists(file_name):
                os.rename(file_name, new_file)
            else:
                print(f"File not found: {file_name}")
            
            print(f"Downloaded audio file: {new_file}")  # Debug statement
            return new_file
    except Exception as e:
        print(f"Error downloading audio: {e}")  # Debug statement
        raise

def blog_list(request) :
    blog_articles = BlogPost.objects.filter(user = request.user)
    return render(request, 'all-blogs.html', {'blog_articles': blog_articles})

def blog_details(request, pk) :
    blog_article_detail = BlogPost.objects.get(id = pk)
    if request.user == blog_article_detail.user :
        return render(request, "blog-details.html", {'blog_article_detail' : blog_article_detail})
    else :
        return redirect('/')

@login_required
def index(request) :
    return render(request, 'index.html')

def user_signup(request) :
    if request.method == 'POST' :
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST['password']
        repeatpassword = request.POST['repeatPassword']
        
        if password == repeatpassword :
            try :
                user = User.objects.create_user(username=username, email=email, password=password)
                user.save()
                # login(request, user)
                return redirect('login')
                
            except :
                error_msg = 'Invalid password'
                return render(request, 'signup.html',  {'error_message' : error_msg})
        else :
            error_msg = 'Invalid password'
            return render(request, 'signup.html',  {'error_message' : error_msg})
        
    else :
        return render(request, 'signup.html')

def user_logout(request) :
    logout(request)
    return redirect('/')

def home(request) :
    if request.method == 'GET' :
        return redirect('/')

def home_blog(request, pk) :
    if request.method == 'GET' :
        return redirect('/')

def user_login(request) :
    if request.method == 'POST' :
        username = request.POST['username']
        password = request.POST['password']
        if username and password :
            user = authenticate(request, username=username, password=password)
            if user is not None :
                login(request, user)
                return redirect('/', {'username' : username})
            else :
                error_msg = 'Invalid username or password'
                return render(request, 'login.html', {'error_message' : error_msg})
    else :
        return render(request,'login.html')