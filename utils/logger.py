import logging
import os


# =========================
# CREATE LOG DIRECTORY
# =========================
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


# =========================
# LOGGER CONFIGURATION
# =========================
LOG_FILE = os.path.join(LOG_DIR, "app.log")

logger = logging.getLogger("AI_Evaluator")
logger.setLevel(logging.INFO)


# =========================
# FORMATTER
# =========================
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


# =========================
# FILE HANDLER
# =========================
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)


# =========================
# CONSOLE HANDLER
# =========================
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)


# =========================
# ADD HANDLERS (avoid duplicates)
# =========================
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


# =========================
# LOG FUNCTIONS
# =========================

def log_info(message):
    logger.info(message)


def log_error(message):
    logger.error(message)


def log_warning(message):
    logger.warning(message)


def log_debug(message):
    logger.debug(message)


# =========================
# OPTIONAL: LOG REQUEST DATA
# =========================

def log_request(student_id, question):
    logger.info(f"Request received | Student ID: {student_id} | Question: {question[:50]}")


def log_result(student_id, score):
    logger.info(f"Evaluation completed | Student ID: {student_id} | Score: {score}")