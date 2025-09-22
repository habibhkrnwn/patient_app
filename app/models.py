from sqlalchemy import Column, Integer, String, Date, Text, func
from sqlalchemy.orm import relationship
from sqlalchemy.sql.sqltypes import DateTime
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="admin")  # 'dokter' or 'admin'
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    nama = Column(String(120), nullable=False)
    tanggal_lahir = Column(Date, nullable=True)
    tanggal_kunjungan = Column(Date, nullable=False)
    diagnosis = Column(Text, nullable=True)
    tindakan = Column(Text, nullable=True)
    dokter = Column(String(120), nullable=True)
