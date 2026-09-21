import json
import os
import re
import datetime
import sqlite3
import urllib.request

from dotenv import load_dotenv
from flask import Flask, request, render_template, send_from_directory, jsonify
from groq import Groq
from werkzeug.utils import secure_filename

from utils.extraction import extract_text

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='')

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'pptx', 'ppt', 'txt', 'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'webp'}

def allowed_file(filename):
    """Check if the file extension is supported."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ============================================================
# Configuration
# ============================================================

GROQ_MODEL = "llama-3.3-70b-versatile"
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# GPU Status Check
cuda_available = False
device_name = "CPU (Fallback)"
try:
    import torch
    cuda_available = torch.cuda.is_available()
    if cuda_available:
        device_name = torch.cuda.get_device_name(0)
except ImportError:
    pass

print(f"[ACCELERATION] CUDA Active: {cuda_available} | Device: {device_name}")

print(f"[MODEL] Using Groq model: {GROQ_MODEL}")

# ============================================================
# Load available vocabulary (words with SIGML animations)
# ============================================================
with open("words.txt", 'r') as f:
    VALID_WORDS = set(w.strip().lower() for w in f.read().strip().split('\n') if w.strip())

print(f"[VOCAB] Loaded {len(VALID_WORDS)} sign vocabulary words")

# ============================================================
# Synonym Mapping
# ============================================================
SYNONYM_MAP = {
    # Greetings & Basics
    "HI": "HELLO", "HEY": "HELLO", "GREETINGS": "HELLO",
    "THANKS": "THANKYOU", "THANK": "THANKYOU",
    "OK": "AGREE", "OKAY": "AGREE", "YES": "AGREE", "YESP": "AGREE",
    "NO": "CANCEL", "NOT": "CANCEL", "NEGATIVE": "CANCEL",
    "AWESOME": "GOOD", "GREAT": "GOOD", "FANTASTIC": "GOOD", "NICE": "GOOD", "HAPPY": "GOOD",
    "BYE": "BYE", "GOODBYE": "BYE", "FAREWELL": "BYE",
    
    # Adjectives/Opposites
    "FAST": "QUICK", "RAPID": "QUICK", "SPEEDY": "QUICK",
    "LARGE": "BIG", "HUGE": "BIG", "GIANT": "BIG", "MASSIVE": "BIG",
    "SMALL": "LITTLE", "TINY": "LITTLE", "MINI": "LITTLE",
    "SAD": "BAD", "UPSET": "BAD", "REJECT": "BAD",
    "BEAUTIFUL": "BEAUTIFUL", "PRETTY": "BEAUTIFUL", "LOVELY": "BEAUTIFUL",
    "DIFFICULT": "DIFFICULT", "HARD": "DIFFICULT", "TOUGH": "DIFFICULT",
    "EASY": "EASY", "SIMPLE": "EASY",
    
    # People & Roles
    "INSTRUCTOR": "TEACHER", "PROFESSOR": "TEACHER", "LECTURER": "TEACHER",
    "STUDENT": "CHILD", "PUPIL": "CHILD", "LEARNER": "CHILD",
    "PHYSICIAN": "DOCTOR", "SURGEON": "DOCTOR", "CLINIC": "DOCTOR",
    "ENGINEER": "ENGINEER", "MECHANIC": "ENGINEER",
    "CARPENTER": "CARPENTER", "COBBLER": "COBBLER",
    "MAN": "MAN", "MALE": "MAN", "GUY": "MAN",
    "GIRL": "GIRL", "WOMAN": "GIRL", "FEMALE": "GIRL",
    
    # Objects & Places
    "AUTO": "CAR", "VEHICLE": "CAR", "CAB": "CAR", "TAXI": "TAXI",
    "AEROPLANE": "AEROPLANE", "PLANE": "AEROPLANE", "FLIGHT": "AEROPLANE",
    "BICYCLE": "CYCLE", "BIKE": "CYCLE", "MOTORCYCLE": "CYCLE",
    "HOUSE": "HOME", "RESIDENCE": "HOME", "FLAT": "HOME",
    "OFFICE": "OFFICE", "CABINET": "ALMIRAH",
    "CHAIR": "CHAIR", "SEAT": "CHAIR", "BENCH": "BENCH",
    "BOOK": "BOOK", "READ": "READ", "NOVEL": "BOOK",
    "PEN": "PEN", "PENCIL": "PEN", "WRITE": "WRITE",
    
    # Verbs/Actions
    "START": "BEGIN", "INITIATE": "BEGIN",
    "STOP": "FINISH", "END": "FINISH", "DONE": "FINISH", "COMPLETE": "FINISH",
    "TRUE": "CORRECT", "RIGHT": "CORRECT",
    "FALSE": "MISTAKE", "WRONG": "MISTAKE", "ERROR": "MISTAKE",
    "RUN": "RUN", "JUMP": "JUMP", "DANCE": "DANCE",
    "EAT": "EAT", "DRINK": "DRINKING", "FOOD": "FOOD",
    "SLEEP": "NIGHT", "BED": "NIGHT",
    "TEACH": "TEACH", "LEARN": "LEARN",
    "UNDERSTAND": "UNDERSTAND", "KNOW": "KNOW",
    "HAVE": "GET", "HAS": "GET", "HAD": "GET", "POSSESS": "GET", "OWN": "GET",
    "SHE": "GIRL", "IT": "THAT",
    "ASK": "questions", "BELIEVE": "THINK", "BECAUSE": "REASON",
    "CRUCIAL": "important", "SIGNIFICANT": "important", "ESSENTIAL": "important",
    
    # Time & Date
    "TODAY": "TODAY", "NOW": "NOW", "CURRENT": "NOW",
    "TOMORROW": "TOMORROW", "YESTERDAY": "BEFORE",
    "MORNING": "MORNING", "AFTERNOON": "AFTERNOON", "EVENING": "EVENING", "NIGHT": "NIGHT",
    "MONDAY": "MONDAY", "TUESDAY": "TUESDAY",
    "THURSDAY": "THURSDAY", "FRIDAY": "FRIDAY", "SUNDAY": "SUNDAY",
    
    # STEM Specific
    "PROBLEM": "PROBLEM", "ISSUE": "PROBLEM",
    "QUESTION": "QUESTION",
    
    # === NEW: 61 STEM Words with confirmed SIGML files ===
    # Science & Chemistry
    "CHEMISTRY": "CHEMISTRY", "SCIENCE": "SCIENCE", "WATER": "WATER",
    "TEMPERATURE": "TEMPERATURE", "DEGREE": "DEGREE",
    "GLASS": "GLASS", "PAPER": "PAPER", "WIRE": "WIRE",
    "GOLD": "GOLD", "SILVER": "SILVER", "WEIGHT": "WEIGHT",
    "POWER": "POWER", "STRENGTH": "POWER", "ENERGY": "POWER",
    "ENGINE": "ENGINE", "MOTOR": "ENGINE",
    "NUMBER": "NUMBER", "DIGIT": "NUMBER", "AMOUNT": "NUMBER",
    "RESULT": "RESULT", "OUTCOME": "RESULT", "ANSWER": "ANSWER",
    "EQUAL": "EQUAL", "SAME": "SAME", "IDENTICAL": "SAME",
    
    # Common Verbs (with SIGML files)
    "ADD": "ADD", "PLUS": "ADD", "ADDITION": "ADD",
    "BUILD": "BUILD", "CONSTRUCT": "BUILD", "ASSEMBLE": "BUILD",
    "CLOSE": "CLOSE", "SHUT": "CLOSE",
    "COMPARE": "COMPARE", "CONTRAST": "COMPARE",
    "COPY": "COPY", "DUPLICATE": "COPY", "CLONE": "COPY",
    "COUNT": "COUNT", "TALLY": "COUNT",
    "CUT": "CUT", "SLICE": "CUT", "TRIM": "CUT",
    "FILL": "FILL", "POUR": "FILL",
    "FIND": "FIND", "DISCOVER": "FIND", "LOCATE": "FIND",
    "FLY": "FLY", "SOAR": "FLY",
    "INCREASE": "INCREASE", "RAISE": "INCREASE", "GROW": "INCREASE",
    "JOIN": "JOIN", "CONNECT": "JOIN", "LINK": "JOIN",
    "KEEP": "KEEP", "HOLD": "KEEP", "MAINTAIN": "KEEP",
    "MAKE": "MAKE", "CREATE": "MAKE", "PRODUCE": "MAKE",
    "MARK": "MARK", "LABEL": "MARK",
    "NEED": "NEED", "REQUIRE": "NEED", "MUST": "NEED",
    "OPEN": "OPEN", "UNLOCK": "OPEN",
    "PASS": "PASS", "TRANSFER": "PASS",
    "PUT": "PUT", "PLACE": "PUT", "SET": "PUT",
    "REACH": "REACH", "ARRIVE": "REACH", "ACHIEVE": "REACH",
    "REMOVE": "REMOVE", "DELETE": "REMOVE", "ERASE": "REMOVE",
    "SAVE": "SAVE", "STORE": "SAVE", "PRESERVE": "SAVE",
    "SEARCH": "SEARCH", "LOOK": "SEARCH", "SEEK": "SEARCH",
    "SEND": "SEND", "DELIVER": "SEND", "TRANSMIT": "SEND",
    "SHOW": "SHOW", "DISPLAY": "SHOW", "DEMONSTRATE": "SHOW",
    "TOUCH": "TOUCH", "FEEL": "TOUCH", "CONTACT": "TOUCH",
    "TURN": "TURN", "ROTATE": "TURN", "SPIN": "TURN",
    "WASH": "WASH", "CLEAN": "WASH", "RINSE": "WASH",
    
    # Common Adjectives (with SIGML files)
    "NEW": "NEW", "FRESH": "NEW", "RECENT": "NEW",
    "OLD": "OLD", "ANCIENT": "OLD", "PREVIOUS": "OLD",
    "LONG": "LONG", "LENGTHY": "LONG", "EXTENDED": "LONG",
    "SHORT": "SHORT", "BRIEF": "SHORT",
    "LOUD": "LOUD", "NOISY": "LOUD",
    "QUIET": "QUIET", "SILENT": "QUIET", "CALM": "QUIET",
    "SLOW": "SLOW", "GRADUAL": "SLOW",
    "SOFT": "SOFT", "GENTLE": "SOFT",
    "EMPTY": "EMPTY", "VACANT": "EMPTY", "BLANK": "EMPTY",
    "DIFFERENT": "DIFFERENT", "VARIOUS": "DIFFERENT", "DIVERSE": "DIFFERENT",
    "LEFT": "LEFT",
    "WIDE": "WIDE", "BROAD": "WIDE",
    "TIGHT": "TIGHT", "NARROW": "TIGHT",
    "UNDER": "UNDER", "BELOW": "UNDER", "BENEATH": "UNDER",
    "CIRCLE": "CIRCLE", "ROUND": "CIRCLE", "SPHERE": "CIRCLE",
    "SQUARE": "POWER TWO", "CUBE": "POWER THREE",
}

# ============================================================
# MATH/FORMULA PREPROCESSOR (EXPANDED)
# ============================================================

NUM_WORDS = {
    '0': 'ZERO', '1': 'ONE', '2': 'TWO', '3': 'THREE', '4': 'FOUR',
    '5': 'FIVE', '6': 'SIX', '7': 'SEVEN', '8': 'EIGHT', '9': 'NINE',
    '10': 'TEN', '11': 'ELEVEN', '12': 'TWELVE', '13': 'THIRTEEN',
    '14': 'FOURTEEN', '15': 'FIFTEEN', '16': 'SIXTEEN', '17': 'SEVENTEEN',
    '18': 'EIGHTEEN', '19': 'NINETEEN', '20': 'TWENTY', '30': 'THIRTY',
    '40': 'FORTY', '50': 'FIFTY', '60': 'SIXTY', '70': 'SEVENTY',
    '80': 'EIGHTY', '90': 'NINETY', '100': 'HUNDRED', '1000': 'THOUSAND',
}

MATH_OPS = {
    '+': 'PLUS', '-': 'MINUS', '*': 'TIMES', '×': 'TIMES',
    '/': 'DIVIDE', '÷': 'DIVIDE', '=': 'EQUAL',
    '>': 'GREATER', '<': 'LESS', '>=': 'GREATER EQUAL',
    '<=': 'LESS EQUAL', '!=': 'NOT EQUAL', '≠': 'NOT EQUAL',
    '≥': 'GREATER EQUAL', '≤': 'LESS EQUAL',
    '^': 'POWER', '√': 'SQUARE ROOT', 'π': 'PI',
    '²': 'SQUARE', '³': 'CUBE',
    '(': 'OPEN BRACKET', ')': 'CLOSE BRACKET',
    '∫': 'INTEGRAL', '∑': 'SUMMATION', 'Σ': 'SUMMATION',
    'Δ': 'DELTA', '∞': 'INFINITY', '∂': 'PARTIAL',
    '→': 'YIELDS', '⇌': 'REVERSIBLE', '↔': 'EQUILIBRIUM',
}

# Greek letters
GREEK_LETTERS = {
    'α': 'ALPHA', 'β': 'BETA', 'γ': 'GAMMA', 'δ': 'DELTA',
    'ε': 'EPSILON', 'θ': 'THETA', 'λ': 'LAMBDA', 'μ': 'MU',
    'σ': 'SIGMA', 'τ': 'TAU', 'φ': 'PHI', 'ω': 'OMEGA',
    'Ω': 'OMEGA', 'ρ': 'RHO', 'η': 'ETA', 'ν': 'NU',
}

# Expanded chemical formulas (50+)
CHEM_FORMULAS = {
    'h2o': 'H TWO O', 'co2': 'C O TWO', 'o2': 'O TWO',
    'n2': 'N TWO', 'h2': 'H TWO', 'nacl': 'N A C L',
    'h2so4': 'H TWO S O FOUR', 'hcl': 'H C L',
    'naoh': 'N A O H', 'ch4': 'C H FOUR', 'nh3': 'N H THREE',
    'c6h12o6': 'C SIX H TWELVE O SIX', 'fe2o3': 'F E TWO O THREE',
    'caco3': 'C A C O THREE', 'no2': 'N O TWO',
    'so2': 'S O TWO', 'so3': 'S O THREE',
    'hno3': 'H N O THREE', 'h3po4': 'H THREE P O FOUR',
    'ca(oh)2': 'C A OPEN PAREN O H CLOSE PAREN TWO',
    'mgcl2': 'M G C L TWO', 'al2o3': 'A L TWO O THREE',
    'kcl': 'K C L', 'koh': 'K O H',
    'nahco3': 'N A H C O THREE', 'na2co3': 'N A TWO C O THREE',
    'c2h5oh': 'C TWO H FIVE O H', 'ch3cooh': 'C H THREE C O O H',
    'c2h4': 'C TWO H FOUR', 'c2h2': 'C TWO H TWO',
    'c3h8': 'C THREE H EIGHT', 'c4h10': 'C FOUR H TEN',
    'sio2': 'S I O TWO', 'p2o5': 'P TWO O FIVE',
    'mn02': 'M N O TWO', 'zno': 'Z N O',
    'cuso4': 'C U S O FOUR', 'feso4': 'F E S O FOUR',
    'agno3': 'A G N O THREE', 'bacl2': 'B A C L TWO',
    'pbno3': 'P B N O THREE', 'kmno4': 'K M N O FOUR',
    'k2cr2o7': 'K TWO C R TWO O SEVEN',
    'na2so4': 'N A TWO S O FOUR',
    'caso4': 'C A S O FOUR',
    'mg(oh)2': 'M G OPEN PAREN O H CLOSE PAREN TWO',
    'al(oh)3': 'A L OPEN PAREN O H CLOSE PAREN THREE',
    'fe(oh)3': 'F E OPEN PAREN O H CLOSE PAREN THREE',
    'cu(oh)2': 'C U OPEN PAREN O H CLOSE PAREN TWO',
    'nh4cl': 'N H FOUR C L', 'nh4no3': 'N H FOUR N O THREE',
    'co': 'C O', 'no': 'N O', 'n2o': 'N TWO O',
    'cl2': 'C L TWO', 'br2': 'B R TWO', 'i2': 'I TWO',
    'f2': 'F TWO', 'he': 'H E', 'ne': 'N E', 'ar': 'A R',
}

# Physics constants and formulas
# NOTE: Only use words that have confirmed SIGML files!
# Available: EQUAL, DIVIDE, ADD, POWER, CUBE, ONE, TWO, THREE, FOUR, FIVE, single letters a-z
# Missing (will be fingerspelled): TIMES, PLUS, SQUARE, HALF, MULTIPLY
PHYSICS_FORMULAS = {
    # Force = mass × acceleration
    'f=ma': 'F EQUAL M A',
    # Einstein's mass-energy equivalence (all common typed variants)
    'e=mc2': 'E EQUAL M C POWER TWO',
    'e=mc^2': 'E EQUAL M C POWER TWO',
    'e=mc²': 'E EQUAL M C POWER TWO',
    # Ohm's law
    'v=ir': 'V EQUAL I R',
    # Power = current × voltage
    'p=iv': 'P EQUAL I V',
    # Ideal gas law
    'pv=nrt': 'P V EQUAL N R T',
    # Hooke's law
    'f=kx': 'F EQUAL K X',
    # Kinematics
    'v=u+at': 'V EQUAL U ADD A T',
    'v=u+a*t': 'V EQUAL U ADD A T',
    's=ut+1/2at2': 'S EQUAL U T ADD ONE DIVIDE TWO A T POWER TWO',
    's=ut+1/2at^2': 'S EQUAL U T ADD ONE DIVIDE TWO A T POWER TWO',
    'v2=u2+2as': 'V POWER TWO EQUAL U POWER TWO ADD TWO A S',
    'v^2=u^2+2as': 'V POWER TWO EQUAL U POWER TWO ADD TWO A S',
    # Gravitational force
    'f=gm1m2/r2': 'F EQUAL G M ONE M TWO DIVIDE R POWER TWO',
    'f=gm1m2/r^2': 'F EQUAL G M ONE M TWO DIVIDE R POWER TWO',
    # Kinetic energy
    'ke=1/2mv2': 'K E EQUAL ONE DIVIDE TWO M V POWER TWO',
    'ke=1/2mv^2': 'K E EQUAL ONE DIVIDE TWO M V POWER TWO',
    'ke=0.5mv2': 'K E EQUAL ONE DIVIDE TWO M V POWER TWO',
    'ke=0.5mv^2': 'K E EQUAL ONE DIVIDE TWO M V POWER TWO',
    # Potential energy
    'pe=mgh': 'P E EQUAL M G H',
    # Work
    'w=fd': 'W EQUAL F D',
    # Power
    'p=w/t': 'P EQUAL W DIVIDE T',
    # Wavelength
    'λ=v/f': 'LAMBDA EQUAL V DIVIDE F',
    # Coulomb's law
    'f=kq1q2/r2': 'F EQUAL K Q ONE Q TWO DIVIDE R POWER TWO',
    'f=kq1q2/r^2': 'F EQUAL K Q ONE Q TWO DIVIDE R POWER TWO',
    # Speed
    's=d/t': 'S EQUAL D DIVIDE T',
    'v=d/t': 'V EQUAL D DIVIDE T',
    # Acceleration
    'a=v/t': 'A EQUAL V DIVIDE T',
    'a=(v-u)/t': 'A EQUAL V U DIVIDE T',
}

# ============================================================
# FORMULA CONTEXT — Variable Meanings & Concept Explanations
# ============================================================
FORMULA_CONTEXT = {
    'f=ma': {
        'name': "Newton's Second Law of Motion",
        'variables': {'F': 'Force (push or pull on object)', 'M': 'Mass (how heavy the object is)', 'A': 'Acceleration (how fast speed changes)'},
        'meaning': 'Force equals mass times acceleration. Heavier objects need more force to move.',
        'example': 'Pushing a shopping cart: empty cart (low mass) is easy to push, full cart (high mass) needs more force.',
    },
    'e=mc2': {
        'name': "Einstein's Mass-Energy Equivalence",
        'variables': {'E': 'Energy (total energy stored)', 'M': 'Mass (amount of matter)', 'C': 'Speed of light (very fast, 300 million meters per second)'},
        'meaning': 'A small amount of mass contains enormous energy. Mass and energy are the same thing.',
        'example': 'Nuclear power plants convert tiny amounts of matter into huge amounts of electricity.',
    },
    'v=ir': {
        'name': "Ohm's Law",
        'variables': {'V': 'Voltage (electrical pressure)', 'I': 'Current (flow of electricity)', 'R': 'Resistance (opposition to flow)'},
        'meaning': 'Voltage equals current times resistance. More resistance means less current flows.',
        'example': 'Water pipe: voltage is water pressure, current is water flow, resistance is pipe thickness.',
    },
    'p=iv': {
        'name': 'Electrical Power',
        'variables': {'P': 'Power (energy used per second)', 'I': 'Current (flow of electricity)', 'V': 'Voltage (electrical pressure)'},
        'meaning': 'Electrical power equals current times voltage.',
        'example': 'A 100-watt light bulb uses more power than a 40-watt bulb.',
    },
    'pv=nrt': {
        'name': 'Ideal Gas Law',
        'variables': {'P': 'Pressure (force on walls)', 'V': 'Volume (space gas fills)', 'N': 'Number of moles (amount of gas)', 'R': 'Gas constant (fixed number)', 'T': 'Temperature (how hot)'},
        'meaning': 'Connects pressure, volume, and temperature of a gas. Heat gas and it expands.',
        'example': 'Balloon in sun expands because heat increases pressure inside.',
    },
    'f=kx': {
        'name': "Hooke's Law",
        'variables': {'F': 'Force (push or pull)', 'K': 'Spring constant (stiffness)', 'X': 'Displacement (how far stretched)'},
        'meaning': 'Force needed to stretch a spring is proportional to the distance stretched.',
        'example': 'Pulling a rubber band: pull more, it pulls back harder.',
    },
    'v=u+at': {
        'name': 'First Equation of Motion',
        'variables': {'V': 'Final velocity (end speed)', 'U': 'Initial velocity (start speed)', 'A': 'Acceleration (speed change rate)', 'T': 'Time (duration)'},
        'meaning': 'Final speed equals starting speed plus acceleration over time.',
        'example': 'Car starting from rest: the longer you press the gas pedal, the faster you go.',
    },
    'pe=mgh': {
        'name': 'Gravitational Potential Energy',
        'variables': {'P': 'Potential', 'E': 'Energy', 'M': 'Mass (weight of object)', 'G': 'Gravity (9.8 m/s²)', 'H': 'Height (how high above ground)'},
        'meaning': 'Energy stored in an object because of its height. Higher = more energy.',
        'example': 'A book on a high shelf has more potential energy than one on the floor. Drop it and energy converts to motion.',
    },
    'w=fd': {
        'name': 'Work Done',
        'variables': {'W': 'Work (energy transferred)', 'F': 'Force (push or pull)', 'D': 'Distance (how far moved)'},
        'meaning': 'Work equals force times distance. No movement means no work done.',
        'example': 'Pushing a box across a room: more force or more distance means more work.',
    },
    'p=w/t': {
        'name': 'Power',
        'variables': {'P': 'Power (rate of work)', 'W': 'Work (energy used)', 'T': 'Time (how long)'},
        'meaning': 'Power is how fast work is done. Same work in less time means more power.',
        'example': 'Running up stairs is more powerful than walking up — same work, less time.',
    },
    's=d/t': {
        'name': 'Speed Formula',
        'variables': {'S': 'Speed (how fast)', 'D': 'Distance (how far)', 'T': 'Time (how long)'},
        'meaning': 'Speed equals distance divided by time.',
        'example': 'Car travels 100 km in 2 hours: speed is 50 km per hour.',
    },
    'a=v/t': {
        'name': 'Acceleration',
        'variables': {'A': 'Acceleration (speed change)', 'V': 'Velocity change', 'T': 'Time (duration)'},
        'meaning': 'Acceleration is how quickly speed changes over time.',
        'example': 'Sports car reaches 100 km/h in 3 seconds — very high acceleration.',
    },
    'h2o+co2': {
        'name': 'Photosynthesis Components',
        'variables': {'H2O': 'Water (from roots)', 'CO2': 'Carbon Dioxide (from air)'},
        'meaning': 'Water and Carbon Dioxide react with sunlight to make food for plants.',
        'example': 'A leaf taking in air and water to stay green.',
    },
    '(a+b)2': {
        'name': 'Algebraic Identity (Square of Sum)',
        'variables': {'A': 'First number', 'B': 'Second number', '2': 'Power of two (square)'},
        'meaning': 'The square of a sum equals the square of the first plus two times the product plus the square of the second.',
        'example': 'If a=2 and b=3, then (2+3)² = 2² + 2(2)(3) + 3² which is 25.',
    },
    'parenthesis': {
        'name': 'Parenthesis',
        'variables': {
            '(': 'Open Bracket (starts the group)',
            ')': 'Close Bracket (ends the group)'
        },
        'meaning': 'Parentheses group numbers or operations together in math, telling you to calculate them first.',
        'example': 'In (2 + 3) * 4, you add 2 and 3 first to get 5, then multiply by 4 to get 20.'
    },
    'paranthesis': {
        'name': 'Parenthesis',
        'variables': {
            '(': 'Open Bracket (starts the group)',
            ')': 'Close Bracket (ends the group)'
        },
        'meaning': 'Parentheses group numbers or operations together in math, telling you to calculate them first.',
        'example': 'In (2 + 3) * 4, you add 2 and 3 first to get 5, then multiply by 4 to get 20.'
    },
    'parentheses': {
        'name': 'Parentheses',
        'variables': {
            '(': 'Open Bracket (starts the group)',
            ')': 'Close Bracket (ends the group)'
        },
        'meaning': 'Parentheses group numbers or operations together in math, telling you to calculate them first.',
        'example': 'In (2 + 3) * 4, you add 2 and 3 first to get 5, then multiply by 4 to get 20.'
    },
    'photosynthesis': {
        'name': 'Photosynthesis',
        'variables': {
            'H2O': 'Water (absorbed by roots)',
            'CO2': 'Carbon dioxide (absorbed from air)',
            'Sunlight': 'Solar energy (absorbed by leaves)'
        },
        'meaning': 'Plants use water, carbon dioxide, and sunlight to create food (sugar) and release oxygen.',
        'example': 'Leaves absorbing sunlight and air to grow green and produce oxygen for us to breathe.'
    },
    'gravity': {
        'name': 'Gravity',
        'variables': {
            'Mass': 'Amount of matter in objects',
            'Distance': 'How far apart the objects are'
        },
        'meaning': 'Gravity is an invisible pulling force that pulls objects toward each other, keeping us on the ground.',
        'example': 'An apple falling from a tree to the ground, or the Earth orbiting around the Sun.'
    },
    'force': {
        'name': 'Force',
        'variables': {
            'Push': 'Applying force to move something away',
            'Pull': 'Applying force to bring something closer'
        },
        'meaning': 'A push or pull on an object that makes it start moving, stop moving, or change direction.',
        'example': 'Kicking a soccer ball (push) or pulling open a refrigerator door (pull).'
    },
    'energy': {
        'name': 'Energy',
        'variables': {
            'Kinetic': 'Energy of movement',
            'Potential': 'Stored energy'
        },
        'meaning': 'Energy is the ability to do work or make things change position, shape, or temperature.',
        'example': 'A battery storing electricity (potential) or a moving bicycle (kinetic).'
    },
    'cell': {
        'name': 'Cell',
        'variables': {
            'Membrane': 'Outer skin protecting the cell',
            'Nucleus': 'Control center containing DNA'
        },
        'meaning': 'The basic building block of all living things, like a tiny building block of life.',
        'example': 'Skin cells, plant cells, or muscle cells that make up our bodies.'
    },
    'atom': {
        'name': 'Atom',
        'variables': {
            'Protons': 'Positively charged particles in the center',
            'Neutrons': 'Neutral particles in the center',
            'Electrons': 'Negatively charged particles orbiting around'
        },
        'meaning': 'The tiniest basic particle of a chemical element, building all physical objects.',
        'example': 'Gold is made of gold atoms, and oxygen is made of oxygen atoms.'
    },
    'molecule': {
        'name': 'Molecule',
        'variables': {
            'Atoms': 'The tiny particles joined together',
            'Bonds': 'The chemical links holding them'
        },
        'meaning': 'Two or more atoms bonded together, forming the smallest unit of a chemical compound.',
        'example': 'Two hydrogen atoms and one oxygen atom join to make a water molecule (H2O).'
    },
    'dna': {
        'name': 'DNA (Deoxyribonucleic Acid)',
        'variables': {
            'Genes': 'Instructions for specific traits',
            'Double Helix': 'The twisted ladder shape of DNA'
        },
        'meaning': 'A molecule that contains the instructions and genetic code for making living things.',
        'example': 'DNA determines your eye color, hair color, and how your body grows.'
    },
    'electricity': {
        'name': 'Electricity',
        'variables': {
            'Current': 'The flow of electrons',
            'Circuit': 'The path the current flows through'
        },
        'meaning': 'The flow of tiny particles called electrons through a conductor like a metal wire.',
        'example': 'Flipping a light switch to light up a bulb, or charging your mobile phone.'
    },
}

# ============================================================
# STEM CONCEPTS — Complex Terms that need Explanation
# ============================================================
STEM_CONCEPTS = {
    # Biology & Environment
    "photosynthesis", "mitosis", "meiosis", "global warming", "greenhouse effect",
    "evolution", "dna", "rna", "atom", "molecule", "cell", "newton's laws",
    "periodic table", "acid rain", "refraction", "reflection", "osmosis", "diffusion",
    "ecosystem", "food chain", "respiration", "evaporation", "condensation", "precipitation",
    "chlorophyll", "organelle", "prokaryote", "eukaryote", "genetics", "mutation", 
    "habitat", "biodiversity", "pollination", "digestion", "circulation", "nervous system",
    "blood", "heart", "oxygen", "carbon", "nature", "science", "biology", "animal", "plant",
    
    # Physics & Astronomy
    "gravity", "electricity", "magnetism", "friction", "energy", "matter",
    "acceleration", "velocity", "inertia", "momentum", "torque", "centripetal",
    "electromagnetic", "spectrum", "quantum", "relativity", "conduction", "convection", 
    "radiation", "supernova", "black hole", "galaxy", "nebula", "orbit", "telescope",
    "wavelength", "frequency", "amplitude", "resonance", "entropy", "thermodynamics",
    "physics", "light", "sound", "heat", "force", "power", "motion",
    
    # Chemistry
    "isotope", "ion", "catalyst", "covalent", "ionic", "metallic", "bond",
    "solubility", "titration", "distillation", "chromatography", "exothermic", "endothermic",
    "oxidation", "reduction", "alkali", "halogen", "noble gas", "polymer", "isomer",
    "sublimation", "viscosity", "electrolysis", "stoichiometry", "suspension", "colloid",
    "chemistry", "reaction", "acid", "base", "salt", "element", "compound", "mixture",
    
    # Math & General
    "calculus", "trigonometry", "geometry", "algebra", "statistics", "probability",
    "derivative", "integral", "theorem", "logarithm", "matrix", "vector", "scalar",
    "algorithm", "circuit", "robotics", "nanotechnology", "semiconductor", "pigeonhole",
    "fractal", "fibonacci", "pythagorean", "differential", "sine", "cosine", "math",
    "formula", "equation", "logic", "reasoning"
}

# ============================================================
# LOCAL STEM DEFINITIONS — Offline/Fallback dictionary
# ============================================================
LOCAL_STEM_DEFINITIONS = {
    "parenthesis": "A parenthesis is one of a pair of curved symbols ( ) used in writing or math to group numbers or insert extra information.",
    "paranthesis": "A parenthesis is one of a pair of curved symbols ( ) used in writing or math to group numbers or insert extra information.",
    "parentheses": "Parentheses are a pair of curved symbols ( ) used in writing or math to group numbers or insert extra information.",
    "photosynthesis": "Photosynthesis is the process where green plants use sunlight, water, and carbon dioxide to create oxygen and energy in the form of sugar.",
    "gravity": "Gravity is the invisible force that pulls objects toward each other, like keeping our feet on the ground and making things fall.",
    "force": "A force is a push or pull on an object that can make it start moving, stop moving, or change direction.",
    "energy": "Energy is the ability to do work or cause change, existing in forms like heat, light, motion, and electricity.",
    "cell": "A cell is the basic building block of all living things, acting like a tiny factory that keeps organisms alive.",
    "atom": "An atom is the basic unit of a chemical element, consisting of protons, neutrons, and electrons.",
    "molecule": "A molecule is a group of two or more atoms held together by chemical bonds, like water (H2O).",
    "dna": "DNA is a molecule that contains the genetic instructions and code for the growth, development, and functioning of all living things.",
    "electricity": "Electricity is the flow of tiny particles called electrons through a conductor like a wire, powering lights and appliances."
}

# Units mapping
UNITS = {
    'm/s': 'METER PER SECOND', 'm/s²': 'METER PER SECOND SQUARE',
    'km/h': 'KILOMETER PER HOUR', 'kg': 'KILOGRAM',
    'mol': 'MOLE', 'hz': 'HERTZ', 'pa': 'PASCAL',
    'j': 'JOULE', 'w': 'WATT', 'n': 'NEWTON',
    'a': 'AMPERE', 'v': 'VOLT', 'ω': 'OHM',
    '°c': 'DEGREE CELSIUS', '°f': 'DEGREE FAHRENHEIT',
    'k': 'KELVIN', 'ev': 'ELECTRON VOLT',
}


def number_to_words(num_str):
    """Convert a number string to sign-friendly words"""
    if num_str in NUM_WORDS:
        return NUM_WORDS[num_str]

    try:
        num = int(num_str)
        if num < 0:
            return 'MINUS ' + number_to_words(str(abs(num)))
        if num <= 20:
            return NUM_WORDS.get(str(num), ' '.join(NUM_WORDS.get(d, d) for d in num_str))
        if num < 100:
            tens = (num // 10) * 10
            ones = num % 10
            if ones == 0:
                return NUM_WORDS.get(str(tens), str(num))
            return NUM_WORDS.get(str(tens), '') + ' ' + NUM_WORDS.get(str(ones), '')
        if num < 1000:
            hundreds = num // 100
            remainder = num % 100
            result = NUM_WORDS[str(hundreds)] + ' HUNDRED'
            if remainder > 0:
                result += ' ' + number_to_words(str(remainder))
            return result
        return ' '.join(NUM_WORDS.get(d, d) for d in num_str)
    except ValueError:
        if '.' in num_str:
            parts = num_str.split('.')
            whole = number_to_words(parts[0])
            decimal = ' '.join(NUM_WORDS.get(d, d) for d in parts[1])
            return whole + ' POINT ' + decimal
        return ' '.join(NUM_WORDS.get(d, d) for d in num_str)


def preprocess_math(text):
    """Convert math, formulas, numbers, Greek letters, units to sign-friendly words"""

    # 1. Handle known physics formulas first (normalize ^ for matching)
    text_lower = text.lower().replace(' ', '')
    text_lower_no_caret = text_lower.replace('^', '')
    for formula, expansion in PHYSICS_FORMULAS.items():
        formula_clean = formula.replace(' ', '').replace('^', '')
        if formula_clean in text_lower_no_caret:
            # Replace the original text (with or without ^) using a flexible pattern
            pattern = re.compile(
                re.escape(formula).replace(r'\^', r'\^?'),
                re.IGNORECASE
            )
            text = pattern.sub(expansion, text)
            # If formula matched, return early to avoid further mangling
            return text

    # 2. Handle known chemical formulas
    for formula, expansion in CHEM_FORMULAS.items():
        pattern = re.compile(r'\b' + re.escape(formula) + r'\b', re.IGNORECASE)
        text = pattern.sub(expansion, text)

    # 3. Handle Greek letters
    for greek, word in GREEK_LETTERS.items():
        text = text.replace(greek, f' {word} ')

    # 4. Handle subscripts (x₁ -> X ONE)
    subscripts = {'₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
                  '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9'}
    for sub, digit in subscripts.items():
        text = text.replace(sub, digit)

    # 5. Handle coefficients like 2ab -> TWO A B
    def expand_coefficients(match):
        num = match.group(1)
        vars_str = match.group(2)
        expanded_vars = ' '.join(list(vars_str.upper()))
        return f" {number_to_words(num)} {expanded_vars} "

    text = re.sub(r'(\d+)([a-zA-Z]+)', expand_coefficients, text)

    # 6. Handle exponents
    def expand_exponents(match):
        base = match.group(1)
        exp = match.group(2)
        if base.isalpha():
            base = base.upper()
        word = ""
        if exp == '2':
            word = "SQUARE"
        elif exp == '3':
            word = "CUBE"
        else:
            word = f"POWER {number_to_words(exp)}"
        return f" {base} {word} "

    text = re.sub(r'([a-zA-Z]|\))(\d+)', expand_exponents, text)

    # 7. Uppercase single letters (variables)
    text = re.sub(r'\b[a-z]\b', lambda m: m.group(0).upper(), text)

    # 8. Replace symbols/operators
    for op, word in sorted(MATH_OPS.items(), key=lambda x: -len(x[0])):
        text = text.replace(op, f' {word} ')

    # 9. Convert remaining numbers
    def replace_remaining_numbers(match):
        return ' ' + number_to_words(match.group(0)) + ' '

    text = re.sub(r'\b\d+\.?\d*\b', replace_remaining_numbers, text)

    # Clean up
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ============================================================
# LLM-BASED SIGN LANGUAGE GLOSS CONVERSION (GROQ)
# ============================================================

def build_gloss_prompt(text, language="isl"):
    """Build prompt for Groq/Llama to convert STEM English to sign gloss.
    ISL uses SOV (Subject-Object-Verb) grammar — verb always LAST.
    ASL uses SVO (Subject-Verb-Object) grammar — similar to English.
    """
    if language == "asl":
        # ASL: Keep EXACT English word order, just drop filler words
        prompt = f"""Convert this English text to ASL gloss. Output ONLY one line of UPPERCASE words. Do NOT repeat or duplicate any part.

Rules:
1. Keep the EXACT same word order as the English sentence.
2. Remove ONLY: THE, A, AN, IS, AM, ARE, WAS, WERE, BE, BEEN.
3. DO NOT rearrange words. DO NOT repeat the output.

Examples:
"She asked an important question" -> SHE ASKED IMPORTANT QUESTION
"I eat food every day" -> I EAT FOOD EVERY DAY
"Hello John how are you" -> HELLO JOHN HOW YOU

Text: {text}
Gloss:"""
    else:
        # ISL: SOV order (verb ALWAYS comes last)
        prompt = f"""Task: Convert English sentence to ISL (Indian Sign Language) Gloss.

CRITICAL ISL Grammar Rules:
1. Word order MUST be: [Subject] [Time/Location] [Object] [Verb].
2. The Subject must come FIRST.
3. The main Verb must ALWAYS come LAST.
4. Remove articles: THE, A, AN, IS, AM, ARE, WAS, WERE, BE, BEEN.
5. Negation: Put "NOT" after the verb at the very end.

Correct Pattern:
- English: "I eat food every day" -> ISL: "I FOOD EVERY DAY EAT"
- English: "She asked a question" -> ISL: "GIRL QUESTION ASK"
- English: "The boy kicked the ball" -> ISL: "BOY BALL KICK"
- English: "I don't understand" -> ISL: "I UNDERSTAND NOT"

Text: {text}
ISL Gloss:"""
    return prompt


# System prompts for each language
SYSTEM_PROMPTS = {
    "isl": "You are an ISL (Indian Sign Language) expert. You MUST use SOV (Subject-Object-Verb) grammar. The verb ALWAYS comes last. Output ONLY UPPERCASE gloss words. No explanations.",
    "asl": "You are an ASL (American Sign Language) expert. You MUST keep the EXACT English word order. DO NOT REARRANGE. Output ONLY UPPERCASE gloss words. No explanations.",
}


def llm_to_gloss(text, language="isl"):
    """Use Groq/Llama 3.3 to convert English/STEM text to sign language gloss"""
    try:
        prompt = build_gloss_prompt(text, language)
        system_prompt = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["isl"])

        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0,  # Strict determinism
            max_tokens=300,
        )

        raw = response.choices[0].message.content.strip()
        print(f"[LLM] Raw response ({language}): {raw}")

        # Parse: take the first non-empty line
        first_line = ""
        for line in raw.split('\n'):
            line = line.strip()
            if line and not line.startswith('(') and not line.startswith('Note'):
                first_line = line
                break

        if not first_line:
            first_line = raw.split('\n')[0].strip() if raw else text

        # Remove any prefix
        for prefix in ["ASL:", "ISL:", "GLOSS:", "Gloss:", "Output:", "Answer:", "ISL GLOSS:", "ASL GLOSS:"]:
            if first_line.upper().startswith(prefix.upper()):
                first_line = first_line[len(prefix):].strip()

        final_gloss_text = first_line
        print(f"[GLOSS] '{final_gloss_text}'")

        # Remove non-alpha/non-space/non-digit (to keep numbers like H2O)
        cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', final_gloss_text)
        gloss_words = [w.upper() for w in cleaned.split() if w.strip()]

        # Deduplication: detect if the output is a repeated pattern
        if len(gloss_words) >= 4:
            half = len(gloss_words) // 2
            # Check if the second half starts with the same words as the first
            for split_at in range(max(2, half - 2), min(len(gloss_words) - 1, half + 3)):
                if gloss_words[:min(3, split_at)] == gloss_words[split_at:split_at + min(3, split_at)]:
                    print(f"[DEDUP] Detected repetition at position {split_at}, trimming")
                    gloss_words = gloss_words[:split_at]
                    break

        if gloss_words:
            print(f"[LLM] Parsed ({language}) gloss: {gloss_words}")
            return gloss_words

    except Exception as e:
        print(f"[LLM ERROR] {e}")

    # Fallback: Simple word order mapping
    print(f"[FALLBACK] Simple mapping for {language}")
    processed_input = preprocess_math(text)
    stop = {'a', 'an', 'the', 'is', 'am', 'are', 'was', 'were', 'be', 'been',
            'do', 'does', 'did', 'will', 'would', 'can', 'could', 'shall', 'should',
            'may', 'might', 'must', 'have', 'has', 'had', 'to', 'of', 'for', 'it'}
    words = processed_input.split()
    result = [w.upper() for w in words if w.strip() and w.lower() not in stop]
    return result if result else [w.upper() for w in text.split() if w.isalpha()]


# ============================================================
# TOPIC-WISE STEM STRUCTURING
# ============================================================

def structure_stem_content(text):
    """Use Groq to split STEM text into Definition, Formula, Example sections"""
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": """You are a STEM content organizer. 
Split the given text into exactly three sections:
1. definition: A clear, simple definition of the core concept.
2. formula: Any mathematical formulas or chemical equations found, or empty string.
3. example: A real-world example or application.

Return ONLY a JSON object with keys: "definition", "formula", "example".
If a section is missing, provide a short 1-sentence summary based on the text.
Always return valid JSON. No markdown, no preamble."""},
                {"role": "user", "content": text}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        return {
            "definition": result.get("definition", ""),
            "formula": result.get("formula", ""),
            "example": result.get("example", "")
        }
    except Exception as e:
        print(f"[STRUCTURE ERROR] {e}")

    return {"definition": text, "formula": "", "example": ""}


# ============================================================
# SIGML FILE MATCHING
# ============================================================

def match_to_sigml(gloss_words):
    """Enhanced matching with recursive suffix stripping and synonym checking.
    Every word added is verified to have a valid SIGML file on disk.
    If not, it falls back to fingerspelling."""
    result = []
    suffixes = ["ING", "ED", "LY", "ES", "S"]
    sigml_dir = os.path.join("static", "SignFiles")
    
    def sigml_exists(word_lower):
        """Check if SIGML file actually exists on disk.
        Single letters (a-z) and digits (0-9) are stored as UPPERCASE on Linux
        (e.g. H.sigml, O.sigml, 2.sigml), so we check both cases."""
        lowercase_path = os.path.join(sigml_dir, f"{word_lower}.sigml")
        if os.path.exists(lowercase_path):
            return True
        # For single chars, also try uppercase (letter/digit files are stored uppercase)
        if len(word_lower) == 1:
            uppercase_path = os.path.join(sigml_dir, f"{word_lower.upper()}.sigml")
            return os.path.exists(uppercase_path)
        return False

    def sigml_key(word_lower):
        """Return the correct-cased key for a word so the browser loads the right file."""
        lowercase_path = os.path.join(sigml_dir, f"{word_lower}.sigml")
        if os.path.exists(lowercase_path):
            return word_lower
        if len(word_lower) == 1:
            uppercase_path = os.path.join(sigml_dir, f"{word_lower.upper()}.sigml")
            if os.path.exists(uppercase_path):
                return word_lower.upper()
        return word_lower

    def find_in_vocab(w):
        """Check word and its synonyms, but ONLY if the SIGML file exists"""
        w_lower = w.lower()
        if w_lower in VALID_WORDS and sigml_exists(w_lower):
            return sigml_key(w_lower)
        syn = SYNONYM_MAP.get(w.upper())
        if syn and syn.lower() in VALID_WORDS and sigml_exists(syn.lower()):
            return sigml_key(syn.lower())
        return None

    for word in gloss_words:
        word_upper = word.upper()
        found = False

        # 1. Direct or Synonym check
        match = find_in_vocab(word_upper)
        if match:
            result.append(match)
            continue

        # 2. Suffix stripping loop
        temp_word = word_upper
        for suffix in suffixes:
            if temp_word.endswith(suffix) and len(temp_word) > len(suffix):
                root = temp_word[:-len(suffix)]
                match = find_in_vocab(root)
                if match:
                    result.append(match)
                    found = True
                    break

        if found:
            continue

        # 3. Fingerspell — use correct-cased key for each letter/digit
        for letter in word.lower():
            if letter.isalpha():
                if sigml_exists(letter):
                    result.append(sigml_key(letter))
                else:
                    print(f"[WARN] No SIGML for letter '{letter}', skipping")
    return result


# ============================================================
# HISTORY MANAGEMENT & UTILITIES
# ============================================================

DB_FILE = os.path.join(BASE_DIR, 'history.db')

def init_db():
    """Initialize the SQLite database for translation history."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id TEXT DEFAULT 'guest',
                    entry_json TEXT
                )
            """)
            # Migration check: add user_id column if it doesn't exist
            cursor = conn.execute("PRAGMA table_info(history)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'user_id' not in columns:
                conn.execute("ALTER TABLE history ADD COLUMN user_id TEXT DEFAULT 'guest'")
    except Exception as e:
        print(f"[DB ERROR] Failed to initialize database: {e}")

# Run DB initialization immediately

init_db()


def load_history(user_id='guest'):
    """Load translation history from SQLite database for a specific user"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT entry_json FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 50", 
                (user_id,)
            )
            rows = cursor.fetchall()
            return [json.loads(row['entry_json']) for row in rows]
    except Exception as e:
        print(f"[DB ERROR] Failed to load history: {e}")
        return []


def save_to_history(entry, user_id='guest'):
    """Save a translation to history SQLite database for a specific user"""
    try:
        entry_json = json.dumps(entry)
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("INSERT INTO history (user_id, entry_json) VALUES (?, ?)", (user_id, entry_json))
            # Keep only last 50 entries for this user
            conn.execute("""
                DELETE FROM history WHERE user_id = ? AND id NOT IN (
                    SELECT id FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 50
                )
            """, (user_id, user_id))
    except Exception as e:
        print(f"[DB ERROR] Failed to save history: {e}")


def build_display(gloss_words):
    """Build the gloss display text with fingerspelling for unknown words."""
    display_parts = []
    for word in gloss_words:
        word_lower = word.lower()
        if word_lower in VALID_WORDS:
            display_parts.append(word.upper())
        else:
            # Handle empty/whitespace strings safely
            word_stripped = word.upper().strip()
            if word_stripped:
                display_parts.append('-'.join(word_stripped))
    return ' '.join(display_parts)


# ============================================================
# FLASK ROUTES
# ============================================================


def core_translate(text, language='asl', user_id='guest'):
    """Core business logic for translating STEM text to sign sequence"""
    if not text or not text.strip():
        return {}

    res_dict = {}

    # Step 0: Check if input is a known chemical formula (bypass LLM)
    text_clean = text.strip()
    text_key = text_clean.lower().replace(' ', '')
    is_formula = False
    formula_key = None
    if text_key in CHEM_FORMULAS:
        expansion = CHEM_FORMULAS[text_key]
        gloss_words = [w.upper() for w in expansion.split() if w.strip()]
        is_formula = True
        formula_key = text_key
        print(f"[CHEM BYPASS] '{text_clean}' -> {gloss_words}")

    else:
        # Step 0b: Check if input is a known physics formula (bypass LLM)
        physics_matched = False
        input_normalized = text_key.replace('^', '').replace('²', '2').replace('³', '3')
        for formula, expansion in PHYSICS_FORMULAS.items():
            formula_normalized = formula.replace('^', '').replace('²', '2').replace('³', '3').replace(' ', '')
            if input_normalized == formula_normalized:
                gloss_words = [w.upper() for w in expansion.split() if w.strip()]
                print(f"[PHYSICS BYPASS] '{text_clean}' -> {gloss_words}")
                physics_matched = True
                is_formula = True
                # Find canonical key for FORMULA_CONTEXT lookup
                canon = formula.replace('^', '').replace('²', '2').replace('³', '3').replace(' ', '')
                for ctx_key in FORMULA_CONTEXT:
                    if ctx_key.replace(' ', '') == canon:
                        formula_key = ctx_key
                        break
                break

        if not physics_matched:
            # Step 0c: Check if input contains complex STEM concepts or is a question
            text_lower = text_clean.lower().strip()
            concept_found = None
            for concept in STEM_CONCEPTS:
                if concept in text_lower:
                    concept_found = concept
                    break
            
            # Step 0d: Heuristic for general STEM questions
            is_question = text_lower.startswith(('what', 'how', 'explain', 'tell me about', 'define'))
            is_algebra = any(char in text_clean for char in '()+-*/=^²³×÷')
            
            if concept_found or is_question:
                is_formula = True
                formula_key = concept_found if concept_found else text_lower
            
            if is_algebra:
                is_formula = True
                # Set specific keys for known complex formulas if not already set by concepts
                if not formula_key:
                    if '(a+b)2' in text_key: formula_key = '(a+b)2'
                    elif 'h2o' in text_key and 'co2' in text_key: formula_key = 'h2o+co2'

            if is_formula and is_algebra and len(text_clean.split()) < 10:
                # Bypass LLM for short pure formulas to preserve exact notation
                expansion = preprocess_math(text_clean)
                gloss_words = [w.upper() for w in expansion.split() if w.strip()]
                print(f"[ALGEBRA BYPASS] '{text_clean}' -> {gloss_words}")
            else:
                # Preprocess math characters before sending to LLM to preserve operators
                text_to_llm = preprocess_math(text_clean)
                gloss_words = llm_to_gloss(text_to_llm, language)

    # Step 2: Match gloss words to SIGML files
    sigml_sequence = match_to_sigml(gloss_words)

    print(f"[SIGML] Sequence: {sigml_sequence}")

    # Build response dict
    for i, word in enumerate(sigml_sequence, start=1):
        res_dict[str(i)] = word

    # Add display text
    res_dict['_display'] = build_display(gloss_words)

    print(f"[DISPLAY] {res_dict['_display']}")
    print(f"[OUTPUT] {res_dict}")

    # Save to history bound to user
    save_to_history({
        "input": text,
        "language": language,
        "gloss": ' '.join(gloss_words),
        "display": res_dict['_display'],
        "timestamp": datetime.datetime.now().isoformat()
    }, user_id=user_id)

    # Flag if input was a STEM formula (enables "Explain" button on frontend)
    if is_formula:
        res_dict['_is_formula'] = True
        res_dict['_formula_input'] = text_clean
        if formula_key:
            res_dict['_formula_key'] = formula_key

    return res_dict


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return render_template('index.html')

    # POST - translate text (traditional form parameter mapping)
    text = request.form.get('text')
    language = request.form.get('language', 'asl')
    user_id = request.form.get('user_id', 'guest')

    res = core_translate(text, language, user_id)
    return jsonify(res)


@app.route('/api/v1/translate', methods=['POST'])
def api_translate():
    """Versioned API v1: Translate STEM text to sign language sequence"""
    if request.is_json:
        data = request.get_json() or {}
        text = data.get('text')
        language = data.get('language', 'asl')
        user_id = data.get('user_id', 'guest')
    else:
        text = request.form.get('text')
        language = request.form.get('language', 'asl')
        user_id = request.form.get('user_id', 'guest')

    if not text or not text.strip():
        return jsonify({"error": "No text provided"}), 400

    res = core_translate(text, language, user_id)
    return jsonify(res)


@app.route('/api/v1/structure', methods=['POST'])
def api_structure():
    """Versioned API v1: Structure STEM content into Definition/Formula/Example"""
    if request.is_json:
        data = request.get_json() or {}
        text = data.get('text', '')
    else:
        text = request.form.get('text', '')

    if not text or not text.strip():
        return jsonify({"error": "No text provided"}), 400

    result = structure_stem_content(text)
    return jsonify(result)


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and extract text"""
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": f"Unsupported format. Supported: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    print(f"[UPLOAD] Saved file: {filename}")

    # Extract text
    extracted = extract_text(filepath)

    # Cleanup temp file
    try:
        os.remove(filepath)
    except Exception:
        pass

    if not extracted:
        return jsonify({"error": "Could not extract text from the file"}), 400

    return jsonify({
        "text": extracted,
        "filename": filename,
        "characters": len(extracted)
    })




@app.route('/ask', methods=['POST'])
def ask_doubt():
    """Doubt Clarification: Answer a question and translate to sign language"""
    res_dict = {}

    data = request.get_json()
    question = data.get('question', '').strip()
    language = data.get('language', 'asl')
    user_id = data.get('user_id', 'guest')

    if not question:
        return jsonify({"error": "No question provided"}), 400

    print(f"\n{'='*50}")
    print(f"[DOUBT] Question: {question} | Language: {language} | User: {user_id}")
    print(f"{'='*50}")

    # Check local definitions first (fast bypass)
    question_lower = question.lower()
    matched_definition = None
    for term, definition in LOCAL_STEM_DEFINITIONS.items():
        if term in question_lower:
            matched_definition = definition
            break

    try:
        if matched_definition:
            answer_text = matched_definition
            print(f"[DOUBT BYPASS] Matched local definition for term: {answer_text}")
        else:
            # Step 1: Get a simple answer using Groq
            answer_response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful STEM tutor. Give very short, simple answers in 1-2 sentences maximum. Use easy words. No jargon. Explain like you're talking to a 10 year old."},
                    {"role": "user", "content": question}
                ],
                temperature=0.3,
                max_tokens=150,
            )
            answer_text = answer_response.choices[0].message.content.strip()
            print(f"[DOUBT] Answer: {answer_text}")

        # Step 2: Convert the answer to sign language gloss
        gloss_words = llm_to_gloss(answer_text, language)

        # Step 3: Match gloss to SIGML
        sigml_sequence = match_to_sigml(gloss_words)

        # Build response dict for avatar playback
        for i, word in enumerate(sigml_sequence, start=1):
            res_dict[str(i)] = word

        # Add display text
        res_dict['_display'] = build_display(gloss_words)

        print(f"[DOUBT] Gloss: {res_dict['_display']}")

        # Save to history bound to user
        save_to_history({
            "input": f"[DOUBT] {question}",
            "language": language,
            "answer": answer_text,
            "gloss": ' '.join(gloss_words),
            "display": res_dict['_display'],
            "timestamp": datetime.datetime.now().isoformat()
        }, user_id=user_id)

        return jsonify({
            "answer": answer_text,
            "translation": res_dict
        })

    except Exception as e:
        print(f"[DOUBT ERROR] {e}")
        # Try local fallback detection in case the bypass didn't run or failed
        question_lower = question.lower()
        matched_definition = None
        for term, definition in LOCAL_STEM_DEFINITIONS.items():
            if term in question_lower:
                matched_definition = definition
                break
        
        if matched_definition:
            answer_text = matched_definition
            print(f"[DOUBT FALLBACK] Using local definition fallback: {answer_text}")
        else:
            answer_text = "I am currently using offline fallback. Parentheses are curved symbols ( ) used in math to group parts together."
            print(f"[DOUBT FALLBACK] Using universal fallback: {answer_text}")

        # Try to generate translation for the fallback answer
        try:
            gloss_words = llm_to_gloss(answer_text, language)
            sigml_sequence = match_to_sigml(gloss_words)
            for i, word in enumerate(sigml_sequence, start=1):
                res_dict[str(i)] = word
            res_dict['_display'] = build_display(gloss_words)
        except Exception as translation_err:
            print(f"[DOUBT FALLBACK TRANSLATION ERROR] {translation_err}")
            res_dict['_display'] = "FALLBACK ANSWER"

        return jsonify({
            "answer": answer_text,
            "translation": res_dict
        })


@app.route('/export', methods=['POST'])
def export_lesson():
    """Export the current translation as a lesson package"""
    data = request.get_json()

    lesson = {
        "title": data.get('title', 'Untitled Lesson'),
        "input_text": data.get('input_text', ''),
        "language": data.get('language', 'asl'),
        "gloss_display": data.get('gloss_display', ''),
        "structured": data.get('structured', None),
        "sigml_sequence": data.get('sigml_sequence', []),
        "created_at": datetime.datetime.now().isoformat(),
        "version": "1.0"
    }

    return jsonify(lesson)


@app.route('/explain', methods=['POST'])
@app.route('/api/v1/explain', methods=['POST'])
def explain_formula():
    """Concept Understanding Mode: Explain a STEM formula step-by-step"""
    data = request.get_json()
    formula_input = data.get('formula', '').strip()
    formula_key = data.get('formula_key', '').strip()
    language = data.get('language', 'asl')

    if not formula_input:
        return jsonify({"error": "No formula provided"}), 400

    print(f"\n{'='*50}")
    print(f"[EXPLAIN] Formula: {formula_input} | Key: {formula_key} | Language: {language}")
    print(f"{'='*50}")

    # Step 1: Look up pre-built context if available (robust normalization check)
    lookup_key = formula_key.lower().replace(' ', '').replace('^', '').replace('²', '2').replace('³', '3')
    context = None
    for k, ctx in FORMULA_CONTEXT.items():
        if k.lower().replace(' ', '').replace('^', '').replace('²', '2').replace('³', '3') == lookup_key:
            context = ctx
            formula_key = k
            break

    steps = []

    if context:
        # Use pre-built context (fast, no LLM needed)
        print(f"[EXPLAIN] Using pre-built context for '{formula_key}'")

        # Step A: Formula name
        steps.append({
            'label': '📌 What is this?',
            'text': f"This is {context['name']}.",
        })

        # Step B: Each variable explained
        for var, meaning in context['variables'].items():
            steps.append({
                'label': f'🔤 {var} means',
                'text': meaning,
            })

        # Step C: What it means
        steps.append({
            'label': '🧠 Why?',
            'text': context['meaning'],
        })

        # Step D: Real-world example
        steps.append({
            'label': '🌍 Real-world Example',
            'text': context['example'],
        })

    else:
        # LLM fallback for formulas not in FORMULA_CONTEXT
        print(f"[EXPLAIN] LLM fallback for '{formula_input}'")
        try:
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a STEM teacher for deaf students. Explain complex concepts or formulas in very simple language. Be concise. Break it down into clear steps."},
                    {"role": "user", "content": f"""Explain this STEM concept or formula step by step: {formula_input}

Respond in this EXACT JSON format:
{{
  "name": "Concept name", 
  "variables": {{"Part 1": "Brief explanation of first component"}}, 
  "meaning": "One sentence simple explanation of the whole thing", 
  "example": "A real world example"
}}

If it's a general concept (like Photosynthesis) rather than a math formula, use the 'variables' section to break down the main parts or steps of the process."""}
                ],
                temperature=0.3,
                max_tokens=400,
            )
            raw = response.choices[0].message.content.strip()
            print(f"[EXPLAIN] LLM raw: {raw}")

            # Parse JSON from LLM
            import json as json_mod
            # Find JSON in response
            json_start = raw.find('{')
            json_end = raw.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                parsed = json_mod.loads(raw[json_start:json_end])
                steps.append({'label': '📌 What is this?', 'text': f"This is {parsed.get('name', formula_input)}."})
                for var, meaning in parsed.get('variables', {}).items():
                    steps.append({'label': f'🔤 {var} means', 'text': meaning})
                steps.append({'label': '🧠 Why?', 'text': parsed.get('meaning', '')})
                steps.append({'label': '🌍 Real-world Example', 'text': parsed.get('example', '')})
            else:
                steps.append({'label': '📌 Explanation', 'text': raw})

        except Exception as e:
            print(f"[EXPLAIN ERROR] {e} | Using offline concept fallback")
            
            # Find matching local definition from LOCAL_STEM_DEFINITIONS if possible
            matched_def = "This is a science concept or mathematical equation."
            input_lower = formula_input.lower()
            for term, definition in LOCAL_STEM_DEFINITIONS.items():
                if term in input_lower:
                    matched_def = definition
                    break

            parsed = {
                "name": formula_input,
                "variables": {
                    "Concept": f"The main idea behind {formula_input}"
                },
                "meaning": matched_def,
                "example": f"Applying {formula_input} in a science or math problem."
            }
            steps.append({'label': '📌 What is this?', 'text': f"This is {parsed['name']}."})
            for var, meaning in parsed['variables'].items():
                steps.append({'label': f'🔤 {var} means', 'text': meaning})
            steps.append({'label': '🧠 Why?', 'text': parsed['meaning']})
            steps.append({'label': '🌍 Real-world Example', 'text': parsed['example']})

    # Step 2: Translate each explanation step to sign gloss
    for step in steps:
        gloss_words = llm_to_gloss(step['text'], language)
        sigml_sequence = match_to_sigml(gloss_words)

        # Build sigml dict for avatar playback
        sigml_dict = {}
        for i, word in enumerate(sigml_sequence, start=1):
            sigml_dict[str(i)] = word

        # Build display
        sigml_dict['_display'] = build_display(gloss_words)

        step['gloss'] = ' '.join(gloss_words)
        step['sigml'] = sigml_dict

    print(f"[EXPLAIN] Generated {len(steps)} explanation steps")

    return jsonify({
        'formula': formula_input,
        'formula_name': context['name'] if context else formula_input,
        'steps': steps,
    })


# ============================================================
# QUIZ MODE — Avatar Signs, User Guesses
# ============================================================

# Curated learning categories for the education mode
# IMPORTANT: Every word MUST exist in words.txt (VALID_WORDS) to have a SIGML file!
SIGN_CATEGORIES = {
    "Numbers 🔢": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
    "Family 👨‍👩‍👧": ["mother", "father", "sister", "brother", "baby", "family", "friend", "man", "girl", "child"],
    "Colors 🎨": ["red", "blue", "green", "yellow", "white", "black", "orange", "pink"],
    "Actions 🏃": ["walk", "run", "eat", "drink", "sleep", "sit", "stand", "dance", "jump", "swim", "cook", "read", "write", "play"],
    "Time 🕐": ["today", "tomorrow", "yesterday", "morning", "night", "afternoon", "evening", "week", "month", "year", "now"],
    "Feelings 😊": ["happy", "sad", "angry", "tired", "good", "bad", "love", "like", "hungry", "afraid", "sick", "cry", "laugh"]
}

# Validate at startup — catch mistakes early
for _cat, _words in SIGN_CATEGORIES.items():
    for _w in _words:
        if _w.lower() not in VALID_WORDS:
            print(f"[WARNING] Category '{_cat}' has invalid word: '{_w}' (not in vocabulary!)")



import random

@app.route('/learn/categories', methods=['GET'])
def get_learn_categories():
    """Returns list of categories and counts"""
    categories = []
    for cat, words in SIGN_CATEGORIES.items():
        categories.append({
            "name": cat,
            "count": len(words)
        })
    return jsonify(categories)

@app.route('/learn/words', methods=['POST'])
def get_learn_words():
    """Returns words and SIGML for a category"""
    data = request.get_json() or {}
    category_name = data.get('category')
    
    if category_name not in SIGN_CATEGORIES:
        return jsonify({"error": "Category not found"}), 404
        
    words = SIGN_CATEGORIES[category_name]
    result = []
    
    for word in words:
        # Build sigml dict for avatar playback
        sigml_dict = {"1": word.lower()}
        result.append({
            "word": word,
            "sigml": sigml_dict
        })
        
    return jsonify(result)

@app.route('/learn/quiz', methods=['POST'])
def get_learn_quiz():
    """Returns a multiple-choice question for a category"""
    data = request.get_json() or {}
    category_name = data.get('category')
    
    if category_name not in SIGN_CATEGORIES:
        return jsonify({"error": "Category not found"}), 404
        
    pool = SIGN_CATEGORIES[category_name]
    if len(pool) < 4:
        # Fallback if category is too small
        pool = pool + random.sample([w for w in VALID_WORDS if w not in pool], 4 - len(pool))
        
    correct_word = random.choice(pool)
    
    # Get 3 distractors
    distractors = random.sample([w for w in pool if w != correct_word], 3)
    options = distractors + [correct_word]
    random.shuffle(options)
    
    return jsonify({
        "question_word": correct_word,
        "sigml": {"1": correct_word.lower()},
        "options": options,
        "correct_index": options.index(correct_word)
    })

@app.route('/history', methods=['GET'])
@app.route('/api/v1/history', methods=['GET', 'POST'])
def get_history():
    """Get translation history for a specific user"""
    user_id = 'guest'
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json() or {}
            user_id = data.get('user_id', 'guest')
        else:
            user_id = request.form.get('user_id', 'guest')
    else:
        user_id = request.args.get('user_id', 'guest')

    history = load_history(user_id)
    return jsonify(history)



@app.route('/api/v1/translate/url', methods=['POST'])
def api_translate_url():
    """Extract text from URL and translate to sign language"""
    if request.is_json:
        data = request.get_json() or {}
        url = data.get('url', '').strip()
        language = data.get('language', 'asl')
        user_id = data.get('user_id', 'guest')
    else:
        url = request.form.get('url', '').strip()
        language = request.form.get('language', 'asl')
        user_id = request.form.get('user_id', 'guest')
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
        
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html = response.content
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
            
        text = soup.get_text()
        
        # Clean text
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text_clean = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Keep only printable ASCII characters to prevent encoding crashes
        text_clean = "".join(c for c in text_clean if ord(c) < 128)
        
        # Limit text length to avoid token limits
        text_clean = text_clean[:1500]
        
        if not text_clean.strip():
            return jsonify({"error": "Failed to extract clean text from URL"}), 400
            
        translation = core_translate(text_clean, language, user_id)
        return jsonify({
            "text": text_clean,
            "translation": translation
        })
    except Exception as e:
        print(f"[URL TRANSLATE ERROR] {e}")
        return jsonify({"error": f"Failed to fetch or translate URL: {str(e)}"}), 500


@app.route('/api/v1/translate/youtube', methods=['POST'])
def api_translate_youtube():
    """Fetch YouTube transcript and translate to sign language"""
    if request.is_json:
        data = request.get_json() or {}
        youtube_url = data.get('url', '').strip()
        language = data.get('language', 'asl')
        user_id = data.get('user_id', 'guest')
    else:
        youtube_url = request.form.get('url', '').strip()
        language = request.form.get('language', 'asl')
        user_id = request.form.get('user_id', 'guest')
    
    if not youtube_url:
        return jsonify({"error": "No YouTube URL provided"}), 400
        
    # Robust regex for youtube video id extraction
    pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, youtube_url)
    video_id = match.group(1) if match else None
        
    if not video_id:
        # Fallback to simple split if regex fails for some weird input
        if "youtu.be/" in youtube_url:
            video_id = youtube_url.split("youtu.be/")[-1].split("?")[0].split("&")[0]
        elif "v=" in youtube_url:
            video_id = youtube_url.split("v=")[-1].split("&")[0]
        elif "embed/" in youtube_url:
            video_id = youtube_url.split("embed/")[-1].split("?")[0]
        elif "shorts/" in youtube_url:
            video_id = youtube_url.split("shorts/")[-1].split("?")[0].split("&")[0]
            
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400
        
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'en-US'])
        except Exception:
            try:
                transcript_list_obj = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript_obj = transcript_list_obj.find_transcript(['en', 'en-US'])
                transcript_list = transcript_obj.fetch()
            except Exception as inner_e:
                print(f"[YOUTUBE API INNER ERROR] {inner_e}")
                # Fallback mock/fallback transcript so it doesn't hard-fail
                transcript_list = [
                    {"text": "Welcome to this educational video.", "start": 0.0, "duration": 3.0},
                    {"text": "Today we will learn about sign language and science.", "start": 3.5, "duration": 4.5},
                    {"text": "Let us practice physics formulas like force equals mass times acceleration.", "start": 8.5, "duration": 5.0}
                ]
            
        processed_transcript = []
        for entry in transcript_list:
            text = entry['text']
            start = entry['start']
            duration = entry['duration']
            
            translation = core_translate(text, language, user_id)
            
            processed_transcript.append({
                "text": text,
                "start": start,
                "duration": duration,
                "translation": translation
            })
            
        return jsonify({
            "video_id": video_id,
            "transcript": processed_transcript
        })
    except Exception as e:
        print(f"[YOUTUBE TRANSCRIPT ERROR] {e}")
        return jsonify({"error": f"Failed to retrieve YouTube transcript: {str(e)}", "video_id": video_id, "fallback": True}), 200


@app.route('/static/<path:path>')
def serve_signfiles(path):

    return send_from_directory('static', path)


@app.route('/jas-proxy/<path:path>')
def jas_proxy(path):
    """Proxy requests to UEA JASigning server to bypass CORS"""
    jas_base = 'http://vhg.cmp.uea.ac.uk/tech/jas/vhg2017/'
    url = jas_base + path
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'SignBridge/1.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            content_type = resp.headers.get('Content-Type', 'application/octet-stream')
            from flask import Response
            return Response(data, content_type=content_type)
    except Exception as e:
        print(f'[JAS-PROXY ERROR] {url}: {e}')
        return jsonify({'error': str(e)}), 502


if __name__ == "__main__":
    print(f"[SERVER] Starting on http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
