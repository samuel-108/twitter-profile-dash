import streamlit as st
import asyncio
import aiohttp
from datetime import datetime
from PIL import Image
from io import BytesIO
import pandas as pd

# Constants
CONCURRENCY_LIMIT = 20
RETRIES = 3
AUTHORIZATION_HEADER = "Bearer " + st.secrets["go_data_api_key"]

# Set the page title and layout
st.set_page_config(page_title="Twitter Profile Dashboard", layout="wide")

def display_user_data(data):
    """Display the user data in Streamlit."""
    # Fetch and display avatar
    avatar_content = data.get('avatar_image')
    if avatar_content:
        avatar_image = Image.open(BytesIO(avatar_content))
        st.image(avatar_image, width=100)

    # Display the name and username
    st.subheader(f"{data.get('name')} (@{data.get('username')})")

    # Display follower count
    followers_count = data.get("followers_count")
    st.metric("Followers", f"{followers_count:,}")

    # Display joined date
    joined_date_str = data.get("joined")
    if joined_date_str:
        joined_date = datetime.strptime(joined_date_str, "%Y-%m-%dT%H:%M:%SZ")
        st.write(f"Joined on {joined_date.strftime('%B %d, %Y')}")

    # Additional information (optional)
    st.write(f"Verified: {'Yes' if data.get('is_verified') else 'No'}")
    st.write(f"Tweets: {data.get('statuses_count')}")
    st.write(f"Following: {data.get('friends_count')}")
    st.write(f"Likes: {data.get('likes_count')}")

async def fetch_user_data(username, session, semaphore):
    """Asynchronously fetch user data and avatar image with retries."""
    api_url = f"https://tw-go-data-api.c2.108capital.ltd/open/profile?username={username}"
    headers = {
        "Authorization": AUTHORIZATION_HEADER
    }
    for attempt in range(RETRIES):
        try:
            async with semaphore:
                async with session.get(api_url, headers=headers) as response:
                    if response.status != 200:
                        raise aiohttp.ClientError(f"HTTP Error {response.status}")
                    data = await response.json()

                    # Fetch avatar image
                    avatar_url = data.get('avatar')
                    if avatar_url:
                        async with session.get(avatar_url) as avatar_response:
                            if avatar_response.status != 200:
                                raise aiohttp.ClientError(f"HTTP Error {avatar_response.status} while fetching avatar image.")
                            avatar_content = await avatar_response.read()
                            data['avatar_image'] = avatar_content
                    else:
                        data['avatar_image'] = None
                    return data
        except Exception as e:
            if attempt < RETRIES - 1:
                await asyncio.sleep(1)
                continue
            else:
                return {"error": f"An error occurred for @{username}: {str(e)}"}

async def main(usernames):
    """Main asynchronous function to fetch data for all usernames."""
    tasks = []
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    async with aiohttp.ClientSession() as session:
        for username in usernames:
            tasks.append(fetch_user_data(username, session, semaphore))
        results = await asyncio.gather(*tasks)
    return results

# Title of the dashboard
st.title("Twitter Profile Dashboard")

# Instruction for the user
st.markdown("Enter Twitter usernames (separated by commas) to fetch their follower counts and joined dates.")

# Input field for usernames
usernames_input = st.text_input("Twitter Usernames", placeholder="elonmusk, jack, satyanadella")

# Initialize an empty list to store data for CSV
csv_data = []

# Button to trigger data fetching
if st.button("Fetch Data"):
    if usernames_input:
        # Split the usernames and remove any extra whitespace
        usernames = [username.strip() for username in usernames_input.split(",") if username.strip()]

        # Run the async function and fetch data
        try:
            results = asyncio.run(main(usernames))
        except RuntimeError:
            # Handle event loop already running issue in Streamlit
            loop = asyncio.get_event_loop()
            results = loop.run_until_complete(main(usernames))

        # Prepare the layout
        max_cols = 4  # Number of profiles per row
        num_profiles = len(usernames)
        rows = (num_profiles + max_cols - 1) // max_cols  # Calculate the number of rows needed

        # Iterate over the results and display data in grid layout
        idx = 0  # Index to keep track of the current profile
        for row in range(rows):
            cols = st.columns(max_cols)
            for col in cols:
                if idx < num_profiles:
                    result = results[idx]
                    with col:
                        if isinstance(result, dict):
                            if 'error' in result:
                                st.error(result['error'])
                            else:
                                display_user_data(result)
                                # Collect data for CSV
                                csv_data.append({
                                    'Username': result.get('username'),
                                    'Twitter Joined Date': result.get('joined'),
                                    'Twitter Followers': result.get('followers_count')
                                })
                        else:
                            st.error(f"An error occurred for @{usernames[idx]}: {str(result)}")
                    idx += 1
                else:
                    # If there are no more profiles, display an empty placeholder
                    with col:
                        st.empty()

        # If there is data, provide a CSV download link
        if csv_data:
            df = pd.DataFrame(csv_data)
            # Convert 'Twitter Joined Date' to a readable format
            df['Twitter Joined Date'] = pd.to_datetime(df['Twitter Joined Date']).dt.strftime('%Y-%m-%d')
            # Convert DataFrame to CSV
            csv = df.to_csv(index=False)
            # Provide download link
            st.download_button(
                label="Download Data as CSV",
                data=csv,
                file_name='twitter_profiles.csv',
                mime='text/csv',
            )
    else:
        st.warning("Please enter at least one username.")
