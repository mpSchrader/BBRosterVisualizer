import json
import re
import fitz
from datetime import datetime, timezone
import pandas as pd

def load_roster(roster_path):
    doc = fitz.open(roster_path)

    roster_path_split = roster_path.split("\\")
    pdf_name = roster_path_split[-1]
    
    return {
        "full_path": roster_path,
        "pdf_name": pdf_name,
        "loaded_pdf": doc
    }

def detect_roster_type(loaded_roster):
    doc = loaded_roster["loaded_pdf"]
    for page_number, page in enumerate(doc, start=1):
        # Extract text in blocks/spans with details
        blocks = page.get_text("dict")["blocks"]
        started_summary = False
    
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"]
                        if text == "SUMMARY":
                            started_summary = True
                        elif started_summary:
                            print(text)
                            if text == "Skill Points":
                                return "bbtc_pl_2025_matched_played"
                            elif text == "Players cost":
                                return "bbtc_pl_2025"
                            elif "Option:" in text:
                                return "bbtc_pl_eurobowl_2025"

        raise RuntimeError(f"Could not identify roster_type for {loaded_roster['full_path']}")


SUMMARY_STEP_MAPPING = {
    "bbtc_pl_2025_matched_played": [
        'Skill Points',
        None,
        'Secondary skills',
        None,
        'Star players',
        None,
    ],
    "bbtc_pl_2025": [
        'Players cost',
        None,
        'Skills cost',
        None,
        'Inducement cost',
        None,
        'Sideline cost',
        None,
        'Primary skills',
        None,
        'Secondary skills',
        None
    ],
    "bbtc_pl_eurobowl_2025": [
        'Players cost',
        None,
        'Skills cost',
        None,
        'Inducement cost',
        None,
        'Sideline cost',
        None,
        'Primary skills',
        None,
        'Secondary skills',
        None
    ],
}


def process_team_pdf(roster_path):
    # Open the PDF
    loaded_roster = load_roster(roster_path)
    doc = loaded_roster["loaded_pdf"]
    pdf_type = detect_roster_type(loaded_roster)
    team_data = {
        'pdf_name': loaded_roster["pdf_name"],
        'pdf_type': pdf_type
    }

    print(team_data)
    
    extraction_step = 'Race'
    for page_number, page in enumerate(doc, start=1):
        # Extract text in blocks/spans with details
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"]
                        color = span["color"]  # RGB, float 0-1 representation
                        # print(f"Page {page_number}: '{text}' Color: {color}")
                        # Adjust extraction step
                        if text == 'SIDELINE':
                            extraction_step = 'Sideline'
                            sideline_ctr = 0
                        elif text == 'INDUCEMENTS':
                            extraction_step = 'Inducements'
                            next_name = None
                        elif text == 'SUMMARY':
                            summary_ctr = 0
                            extraction_step = 'Summary'
                            summary_ctr = -1
    
                        if extraction_step == 'Race':
                            if text == 'COACH NAME':
                                extraction_step = 'Coach'
                                continue
                            if 'Race' in team_data:
                                team_data['Race'] += ' ' + text
                            else:
                                team_data['Race'] = text

                        elif extraction_step == 'Coach':
                            team_data['Coach'] = text
                            extraction_step = 'Team'

                        elif extraction_step == 'Team':
                            if text == 'TEAM NAME':
                                continue
                            elif text == 'SIDELINE':
                                extraction_step = 'Sideline'
                                sideline_ctr = 0
                                
                            elif 'Team' in team_data:
                                team_data['Team'] += ' ' + text
                            else:
                                team_data['Team'] = text

                        elif extraction_step == 'Sideline':
                            sideline_properties = [
                                'Apothecary',
                                'Assistant coaches',
                                'Cheerleaders',
                                'Dedicated fans',
                                'Re-rolls',
                            ]

                            if sideline_ctr >= len(sideline_properties):
                                extraction_step = 'Inducements'
                                continue
                            next_sideline = sideline_properties[sideline_ctr]
                            
                            if text == 'SIDELINE':
                                continue
                            elif text in sideline_properties:
                                if (sideline_ctr == 0) and (text != 'Apothecary'):
                                    sideline_ctr += 1
                                continue
                            else:
                                # print('SAVE', next_sideline, text)
                                team_data[f'Sideline - {next_sideline}'] = text
                                sideline_ctr += 1

                        elif extraction_step == 'Inducements':
                            if text in ['SUMMARY', 'No inducements', 'LEAGUES & SPECIAL']:
                                summary_ctr = 0
                                extraction_step = 'Summary'
                                summary_ctr = -1
                                continue
                            if text == 'INDUCEMENTS':
                                continue
                            if next_name is None:
                                next_name = text
                            else:
                                team_data[f'Inducement - {next_name}'] = text
                                next_name = None

                        elif extraction_step == 'Summary':
                            print(f"SUMMARY {summary_ctr} | {text}")
                            summary_steps = SUMMARY_STEP_MAPPING[pdf_type]
                            if summary_ctr == len(summary_steps):
                                extraction_step = 'Players'
                                player_ctr = -1
                                continue

                            if text == 'SUMMARY':
                                summary_ctr = 0
                                continue
                            elif summary_ctr == -1:
                                continue

                            if pdf_type == "bbtc_pl_eurobowl_2025":
                                if summary_ctr == 0:
                                    team_data[f'Summary - Option'] = text.split(": ")[0]
                                    extraction_step = 'Players'
                                    player_ctr = -1
                                    continue
                                else:
                                    raise NotImplementedError()
                            else:
                                if (summary_ctr % 2) == 1:
                                    team_data[f'Summary - {summary_steps[summary_ctr - 1]}'] = text
                            summary_ctr += 1

                        elif extraction_step == 'Players':
                            if text == 'COST':
                                team_data['Players'] = []
                                player_ctr = 1
                                next_player_property = 'Name'
                                current_player = {
                                    'ctr': player_ctr,
                                    'position_name': None,
                                    'primary_1': None,
                                    'primary_2': None,
                                    'secondary_1': None,
                                    'secondary_2': None,
                                    'star': False,
                                }
                                continue
                            elif player_ctr == -1:
                                continue

                            if re.fullmatch(r"\b\d+k\b", text):
                                team_data['Players'].append(current_player)
                                player_ctr += 1
                                current_player = {
                                    'ctr': player_ctr,
                                    'position_name': None,
                                    'primary_1': None,
                                    'primary_2': None,
                                    'secondary_1': None,
                                    'secondary_2': None,
                                    'star': False,
                                }
                                next_player_property = 'Name'

                            elif next_player_property == 'Name':
                                current_player['position_name'] = " ".join(text.split()[1:])
                                next_player_property = 'Skills'

                            elif next_player_property == 'Skills':
                                if color == 681912:
                                    if current_player['primary_1'] is None:
                                        current_player['primary_1'] = text.strip().strip(',')
                                    elif current_player['primary_2'] is None:
                                        current_player['primary_2'] = text.strip().strip(',')
                                    else:
                                        raise RuntimeError(f'Unexpected Skill | Color: {color} - Text: {text}')
                                if color == 4822027:
                                    if current_player['secondary_1'] is None:
                                        current_player['secondary_1'] = text.strip().strip(',')
                                    elif current_player['secondary_2'] is None:
                                        current_player['secondary_2'] = text.strip().strip(',')
                                    else:
                                        raise RuntimeError(f'Unexpected Skill | Color: {color} - Text: {text}')
                            
                            if text == 'Special skill: ':
                                current_player['star'] = True
                                      
    return team_data