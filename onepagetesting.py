import os
import time
import json
import requests
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Initialize the WebDriver
def init_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--disable-gpu')
    options.add_argument('--headless')  # Run headless to speed up
    driver = webdriver.Chrome(options=options)
    return driver

def search_fmref_id(driver, fmref_id):
    url = f"https://fmref.com/player/{fmref_id}"
    driver.get(url)
    time.sleep(3)  # Adjust sleep as necessary

def extract_team_info(soup):
    team_tag = soup.find('a', href=lambda href: href and 'team' in href)
    if team_tag:
        return team_tag.text.strip()
    else:
        return "Free Agent/No Team"

def fetch_team_for_id(fmref_id):
    if not fmref_id.isdigit():
        return "Not in FM24"
    
    driver = init_driver()
    try:
        search_fmref_id(driver, fmref_id)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        team_name = extract_team_info(soup)
        return team_name
    finally:
        driver.quit()

def extract_data_from_page(url, headers):
    pageTree = requests.get(url, headers=headers)
    pageSoup = BeautifulSoup(pageTree.content, 'html.parser')
    
    PlayersList = []
    TransfermarktIDList = []
    TeamLeftList = []
    TeamJoinedList = []
    FeeList = []
    DateTimeList = []

    rows = pageSoup.find_all('tr', class_=['odd', 'even'])

    for row in rows:
        hauptlink_elements = row.find_all('td', class_='hauptlink')
        
        player_info = hauptlink_elements[0] if len(hauptlink_elements) > 0 else None
        player_name = player_info.find('a').text if player_info and player_info.find('a') else None
        player_link = player_info.find('a')['href'] if player_info and player_info.find('a') else None
        
        transfermarkt_id = player_link.split('/')[-1] if player_link else None
        
        team_left = hauptlink_elements[1].find('a').text if len(hauptlink_elements) > 1 and hauptlink_elements[1].find('a') else None
        
        team_joined = hauptlink_elements[2].find('a').text if len(hauptlink_elements) > 2 and hauptlink_elements[2].find('a') else None
        
        fee_element = row.find('td', class_='rechts hauptlink')
        fee = fee_element.text.strip() if fee_element else None

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        PlayersList.append(player_name)
        TransfermarktIDList.append(transfermarkt_id)
        TeamLeftList.append(team_left)
        TeamJoinedList.append(team_joined)
        FeeList.append(fee)
        DateTimeList.append(current_time)

    return PlayersList, TransfermarktIDList, TeamLeftList, TeamJoinedList, FeeList, DateTimeList

def load_existing_data(file_path):
    try:
        with open(file_path, 'r') as file:
            data = json.load(file)
        return pd.DataFrame(data)
    except FileNotFoundError:
        return pd.DataFrame(columns=['Player', 'Transfermarkt ID', 'Team Left', 'Team Joined', 'Fee', 'Datetime Retrieved', 'FMRef ID', 'FMRef Team'])

def player_exists(df, player_name):
    return not df[df['Player'] == player_name].empty

def update_fmref_data(players_data):
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(fetch_team_for_id, player['FMRef ID']): player for player in players_data if player['FMRef ID'].isdigit()}
        for future in as_completed(futures):
            player = futures[future]
            try:
                team_name = future.result()
                player["FMRef Team"] = team_name
            except Exception as e:
                print(f"Error fetching team data for FMRef ID: {e}")
                player["FMRef Team"] = "Free Agent/No Team"
    return players_data

def main():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    base_url = "https://www.transfermarkt.co.uk/transfers/neuestetransfers/statistik?ajax=yw1&land_id=0&maxMarktwert=500000000&minMarktwert=0&plus=1&wettbewerb_id=alle&page=1"
    json_file_path = Path('testing/transfers.json')
    json_file_path.parent.mkdir(parents=True, exist_ok=True)

    while True:
        print("Checking for new transfers...")
        existing_df = load_existing_data(json_file_path)
        
        new_data = {
            'Player': [],
            'Transfermarkt ID': [],
            'Team Left': [],
            'Team Joined': [],
            'Fee': [],
            'Datetime Retrieved': [],
            'FMRef ID': [],
            'FMRef Team': []
        }

        players, transfermarkt_ids, team_lefts, team_joineds, fees, datetimes = extract_data_from_page(base_url, headers)
        
        for player, transfermarkt_id, team_left, team_joined, fee, datetime_retrieved in zip(players, transfermarkt_ids, team_lefts, team_joineds, fees, datetimes):
            if not player_exists(existing_df, player):
                new_data['Player'].append(player)
                new_data['Transfermarkt ID'].append(transfermarkt_id)
                new_data['Team Left'].append(team_left)
                new_data['Team Joined'].append(team_joined)
                new_data['Fee'].append(fee)
                new_data['Datetime Retrieved'].append(datetime_retrieved)
                new_data['FMRef ID'].append("N/A")
                new_data['FMRef Team'].append("N/A")

        if new_data['Player']:
            new_df = pd.DataFrame(new_data)
            updated_df = pd.concat([existing_df, new_df], ignore_index=True)
            updated_df_dict = updated_df.to_dict('records')
            updated_df_dict = update_fmref_data(updated_df_dict)
            with open(json_file_path, 'w') as file:
                json.dump(updated_df_dict, file, indent=4)
            print(f"Added {len(new_data['Player'])} new players to {json_file_path}.")
        else:
            print("No new players found.")
        
        print("Waiting for 10 minutes before the next check...")
        time.sleep(600)

if __name__ == "__main__":
    main()
