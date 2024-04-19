from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
Base = declarative_base()

class Wallet(Base):
    __tablename__ = "wallet"
    address = Column(String, primary_key=True, index=True)


# engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
# Our Sessionlocal class
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base.metadata.create_all(bind=engine)

engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=True)

# Create an asynchronous session maker
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession
)