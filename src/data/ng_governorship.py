"""
Nigeria's governorship elections: the 28 states that vote on 6 February 2027 (the other eight hold off-cycle
elections), and each state's 2023 result as the baseline.

2023 results: the leading candidates' shares of the valid vote and the winner, from Wikipedia's summary of the 18
March 2023 governorship elections (INEC's declarations, including Adamawa's and Kebbi's supplementary polls). Abia's
shares are not given there and are left out rather than estimated.
"""
from __future__ import annotations

ELECTION = "ng-2027-gov"
POLLING_DAY = "2027-02-06"
STATES: tuple[str, ...] = ('Abia', 'Adamawa', 'Akwa Ibom', 'Bauchi', 'Benue', 'Borno', 'Cross River', 'Delta', 'Ebonyi', 'Enugu', 'Gombe', 'Jigawa', 'Kaduna', 'Kano', 'Katsina', 'Kebbi', 'Kwara', 'Lagos', 'Nasarawa', 'Niger', 'Ogun', 'Oyo', 'Plateau', 'Rivers', 'Sokoto', 'Taraba', 'Yobe', 'Zamfara')

RESULTS_2023: dict[str, list[dict]] = {
    "Abia": [{"name": "Alex Otti", "party": "LP", "share": None, "won": True}, {"name": "Ikechi Emenike", "party": "APC", "share": None, "won": False}, {"name": "Gregory Ibe", "party": "APGA", "share": None, "won": False}, {"name": "Uche Ikonne", "party": "PDP", "share": None, "won": False}],
    "Adamawa": [{"name": "Ahmadu Umaru Fintiri", "party": "PDP", "share": 50.46, "won": True}, {"name": "Aishatu Dahiru Ahmed", "party": "APC", "share": 46.71, "won": False}],
    "Akwa Ibom": [{"name": "Umo Eno", "party": "PDP", "share": 53.98, "won": True}, {"name": "Bassey Albert Akpan", "party": "YPP", "share": 20.76, "won": False}, {"name": "Akan Udofia", "party": "APC", "share": 19.74, "won": False}],
    "Bauchi": [{"name": "Bala Mohammed", "party": "PDP", "share": 50.78, "won": True}, {"name": "Sadique Abubakar", "party": "APC", "share": 41.79, "won": False}, {"name": "Halliru Dauda Jika", "party": "NNPP", "share": 5.85, "won": False}],
    "Benue": [{"name": "Hyacinth Alia", "party": "APC", "share": 62.61, "won": True}, {"name": "Titus Uba", "party": "PDP", "share": 29.58, "won": False}, {"name": "Herman Hembe", "party": "LP", "share": 5.53, "won": False}],
    "Borno": [{"name": "Babagana Umara Zulum", "party": "APC", "share": 86.1, "won": True}, {"name": "Mohammed Ali Jajari", "party": "PDP", "share": 12.96, "won": False}],
    "Cross River": [{"name": "Bassey Otu", "party": "APC", "share": 57.23, "won": True}, {"name": "Sandy Ojang Onor", "party": "PDP", "share": 39.75, "won": False}],
    "Delta": [{"name": "Sheriff Oborevwori", "party": "PDP", "share": 52.43, "won": True}, {"name": "Ovie Omo-Agege", "party": "APC", "share": 34.96, "won": False}, {"name": "Ken Pela", "party": "LP", "share": 6.99, "won": False}],
    "Ebonyi": [{"name": "Francis Nwifuru", "party": "APC", "share": 58.13, "won": True}, {"name": "Ifeanyichukwu Odii", "party": "PDP", "share": 23.41, "won": False}, {"name": "Bernard Odoh", "party": "APGA", "share": 15.24, "won": False}],
    "Enugu": [{"name": "Peter Mbah", "party": "PDP", "share": 44.88, "won": True}, {"name": "Chijioke Edeoga", "party": "LP", "share": 43.95, "won": False}, {"name": "Frank Nweke", "party": "APGA", "share": 5.02, "won": False}, {"name": "Uche Nnaji", "party": "APC", "share": 4.07, "won": False}],
    "Gombe": [{"name": "Muhammad Inuwa Yahaya", "party": "APC", "share": 56.63, "won": True}],
    "Jigawa": [{"name": "Umar Namadi", "party": "APC", "share": 59.89, "won": True}, {"name": "Mustapha Sule Lamido", "party": "PDP", "share": 35.71, "won": False}, {"name": "Aminu Ibrahim Ringim", "party": "NNPP", "share": 3.6, "won": False}],
    "Kaduna": [{"name": "Uba Sani", "party": "APC", "share": 47.2, "won": True}, {"name": "Isah Ashiru", "party": "PDP", "share": 46.49, "won": False}, {"name": "Jonathan Asake", "party": "LP", "share": 3.77, "won": False}],
    "Kano": [{"name": "Abba Kabir Yusuf", "party": "NNPP", "share": 51.55, "won": True}, {"name": "Nasir Yusuf Gawuna", "party": "APC", "share": 45.03, "won": False}],
    "Katsina": [{"name": "Dikko Umaru Radda", "party": "APC", "share": 62.96, "won": True}, {"name": "Garba Yakubu Lado", "party": "PDP", "share": 35.63, "won": False}],
    "Kebbi": [{"name": "Nasir Idris", "party": "APC", "share": 52.37, "won": True}, {"name": "Aminu Bande", "party": "PDP", "share": 46.19, "won": False}],
    "Kwara": [{"name": "AbdulRahman AbdulRazaq", "party": "APC", "share": 59.38, "won": True}, {"name": "Shuaib Abdullahi Yaman", "party": "PDP", "share": 33.77, "won": False}, {"name": "Hakeem Lawal", "party": "SDP", "share": 3.02, "won": False}],
    "Lagos": [{"name": "Babajide Sanwo-Olu", "party": "APC", "share": 65.95, "won": True}, {"name": "Gbadebo Rhodes-Vivour", "party": "LP", "share": 27.03, "won": False}, {"name": "Abdul-Azeez Olajide Adediran", "party": "PDP", "share": 5.4, "won": False}],
    "Nasarawa": [{"name": "Abdullahi Sule", "party": "APC", "share": 53.1, "won": True}, {"name": "David Ombugadu", "party": "PDP", "share": 43.28, "won": False}],
    "Niger": [{"name": "Mohammed Umar Bago", "party": "APC", "share": 53.82, "won": True}, {"name": "Isah Liman Kantigi", "party": "PDP", "share": 44.38, "won": False}],
    "Ogun": [{"name": "Dapo Abiodun", "party": "APC", "share": 42.83, "won": True}, {"name": "Oladipupo Olatunde Adebutu", "party": "PDP", "share": 40.67, "won": False}, {"name": "Olubiyi Otegbeye", "party": "ADC", "share": 14.69, "won": False}],
    "Oyo": [{"name": "Seyi Makinde", "party": "PDP", "share": 63.37, "won": True}, {"name": "Teslim Folarin", "party": "APC", "share": 28.86, "won": False}, {"name": "Adebayo Adelabu", "party": "A", "share": 4.31, "won": False}],
    "Plateau": [{"name": "Caleb Mutfwang", "party": "PDP", "share": 48.62, "won": True}, {"name": "Nentanwe Yilwatda", "party": "APC", "share": 44.55, "won": False}, {"name": "Patrick Dakum", "party": "LP", "share": 5.58, "won": False}],
    "Rivers": [{"name": "Siminalayi Fubara", "party": "PDP", "share": 62.53, "won": True}, {"name": "Tonye Cole", "party": "APC", "share": 19.69, "won": False}, {"name": "Magnus Abe", "party": "SDP", "share": 9.71, "won": False}, {"name": "Beatrice Itubo", "party": "LP", "share": 4.59, "won": False}],
    "Sokoto": [{"name": "Ahmad Aliyu", "party": "APC", "share": 52.48, "won": True}, {"name": "Saidu Umar", "party": "PDP", "share": 46.81, "won": False}],
    "Taraba": [{"name": "Agbu Kefas", "party": "PDP", "share": None, "won": True}, {"name": "Emmanuel Bwacha", "party": "APC", "share": None, "won": False}, {"name": "Yahaya Sani", "party": "NNPP", "share": None, "won": False}],
    "Yobe": [{"name": "Mai Mala Buni", "party": "APC", "share": 71.33, "won": True}, {"name": "Sharif Abdullahi", "party": "PDP", "share": 27.95, "won": False}],
    "Zamfara": [{"name": "Dauda Lawal", "party": "PDP", "share": None, "won": True}, {"name": "Bello Matawalle", "party": "APC", "share": None, "won": False}],
}


def winner_2023(state: str) -> dict | None:
    return next((c for c in RESULTS_2023.get(state, ()) if c["won"]), None)
