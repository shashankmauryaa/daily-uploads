import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def main():
    creds = None
    # The file youtube_token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('youtube_token.json'):
        try:
            creds = Credentials.from_authorized_user_file('youtube_token.json', SCOPES)
        except Exception as e:
            print(f"Error loading existing token: {e}")
            creds = None
            
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing existing token...")
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Failed to refresh token: {e}. Starting new OAuth flow...")
                flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            print("No valid token found. Starting new OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open('youtube_token.json', 'w') as token:
            token.write(creds.to_json())
            print("youtube_token.json generated successfully!")
    else:
        print("Token is already valid.")

if __name__ == '__main__':
    main()
