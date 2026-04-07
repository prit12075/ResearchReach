import logging
from app import create_app
from app.core.config import config
from app.core.database import db
from app.core.email_system import email_system
from app.core.scheduler import start_scheduler

# Setup root logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("professor_finder.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

app = create_app()

if __name__ == "__main__":
    # Start background scheduler
    logger.info("Initializing scheduler...")
    start_scheduler(db, email_system)
    
    logger.info(f"Starting ResearchReach on port {config.FLASK_PORT}")
    app.run(
        host="0.0.0.0",
        port=int(config.FLASK_PORT),
        debug=config.DEBUG,
        use_reloader=False,
    )
