"""
Unified state constants for SmarterVote.
Single source of truth for all state code to name mappings.
"""

# Complete US state and territory mapping
STATE_NAME = {
    "AL": "Alabama",
    "AK": "Alaska", 
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

# Primary election dates by state and year (expandable)
PRIMARY_DATE_BY_STATE = {
    2024: {
        "GA": "2024-05-21",
        "PA": "2024-04-23", 
        "OH": "2024-03-19",
        "CA": "2024-03-05",
        "TX": "2024-03-05",
        "NC": "2024-03-05",
        "VA": "2024-06-18",
        "MO": "2024-08-06",
        "FL": "2024-08-20",
        "NY": "2024-06-25",
    },
    2026: {
        # Will be populated as needed
    }
}