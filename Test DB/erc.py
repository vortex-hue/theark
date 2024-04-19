from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI, HTTPException

# Define the base class for the SQLAlchemy model
Base = declarative_base()

# Define the User model
class Wallet(Base):
    __tablename__ = "wallet"
    address = Column(String, primary_key=True, index=True)


# Set up the database engine
engine = create_engine('sqlite:///./test.db', echo=True)

# Create tables based on the models defined
Base.metadata.create_all(bind=engine)

# Create a session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a FastAPI instance
app = FastAPI()

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Example endpoint to create a new user
@app.post("/users/")
def create_user(name: str, age: int, db = get_db()):
    db_user = User(name=name, age=age)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# Example endpoint to get a user by ID
@app.get("/users/{user_id}")
def read_user(user_id: int, db = get_db()):
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

# Run the server command (to be executed in the terminal, not here)
# uvicorn.run(app, host="127.0.0.1", port=8000)

# Comment out the function calls and method calls in the PCI.
# Uncomment these when the code is finalized and ready to be run.
