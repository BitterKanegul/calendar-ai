from functools import lru_cache
import os
from typing import Optional, List, Union
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application settings with environment-specific configuration."""
    
    # Environment settings
    ENV: str = Field(default="development", description="Environment: development, staging, production")
    DEBUG: bool = Field(default=True, description="Debug mode")
    API_V1_STR: str = Field(default="/api/v1", description="API version prefix")
    
    # CORS settings
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = Field(
        default="http://localhost:3000,http://localhost:8080", 
        description="Comma-separated list of allowed CORS origins"
    )
    
    # Database settings
    DATABASE_URL: str = Field(..., description="Database connection URL")
    
    # Database pool settings
    DB_POOL_SIZE: int = Field(default=20, description="Database pool size")
    DB_MAX_OVERFLOW: int = Field(default=30, description="Database max overflow")
    DB_POOL_TIMEOUT: int = Field(default=30, description="Database pool timeout")
    DB_POOL_RECYCLE: int = Field(default=3600, description="Database pool recycle time")
    DB_POOL_PRE_PING: bool = Field(default=True, description="Database pool pre-ping")

    # Redis settings
    REDIS_URL: str = Field(default="redis://localhost:6379", description="Redis connection URI")
    
    # SSL settings
    DB_SSL_MODE: Optional[str] = Field(default=None, description="Database SSL mode")
    DB_CONNECT_TIMEOUT: int = Field(default=10, description="Database connection timeout")
    
    # Security settings
    SECRET_KEY: str = Field(..., description="Secret key for JWT tokens")
    ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Access token expiration time")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, description="Refresh token expiration time in days")
    
    # Server settings
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=8000, description="Server port")

    # LLM settings
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key")
    
    
    # Logging settings
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    SQL_ECHO: bool = Field(default=False, description="SQL query logging")
    
    # Monitoring settings
    HEALTH_CHECK_ENABLED: bool = Field(default=True, description="Enable health checks")
    METRICS_ENABLED: bool = Field(default=True, description="Enable metrics collection")
    
    # Speech recognition settings
    SPEECH_RECOGNITION_TIMEOUT: int = Field(default=30, description="Speech recognition timeout")

    # Google OAuth2 (for Gmail)
    GOOGLE_CLIENT_ID: Optional[str] = Field(default=None, description="Google OAuth2 client ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = Field(default=None, description="Google OAuth2 client secret")
    GOOGLE_REDIRECT_URI: str = Field(default="http://localhost:8000/auth/google/callback", description="Google OAuth2 redirect URI")

    # Ticketmaster API (Leisure Search)
    TICKETMASTER_API_KEY: Optional[str] = Field(default=None, description="Ticketmaster Discovery API key")

    # Email RAG Pipeline
    CHROMA_PERSIST_DIR: str = Field(default="./data/chroma", description="ChromaDB persistence directory")
    GMAIL_CREDENTIALS_DIR: str = Field(default="./data/gmail_credentials", description="Per-user Gmail credential storage")
    EMBEDDING_MODEL: str = Field(default="all-MiniLM-L6-v2", description="Sentence transformer model for email embeddings")
    EMAIL_INDEX_REFRESH_MINUTES: int = Field(default=15, description="Minimum minutes between email index refreshes")
    
    @field_validator('BACKEND_CORS_ORIGINS', mode='before')
    @classmethod
    def assemble_cors_origins(cls, v):
        """Parse CORS origins from string to list."""
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    @property
    def database_url(self) -> str:
        """Get the database URL, constructing it from components if needed."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        else:
            raise ValueError("DATABASE_URL must be provided")
    
    @property
    def server_host(self) -> str:
        """Get the server host."""
        if self.HOST:
            return self.HOST
        else:
            raise ValueError("HOST must be provided")
    
    @property
    def server_port(self) -> int:
        """Get the server port."""
        if self.PORT:
            return self.PORT
        else:
            raise ValueError("PORT must be provided")
        
    @property
    def redis_url(self) -> str:
        """Get the Redis URL."""
        if self.REDIS_URL:
            return self.REDIS_URL
        else:
            raise ValueError("REDIS_URL must be provided")
    
    @property
    def logging_config(self) -> dict:
        """Get logging configuration."""
        return {
            "level": self.LOG_LEVEL,
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": self.LOG_LEVEL,
                }
            }
        }

    class Config:
        env_file = f".env.{os.getenv('ENV', 'development')}"
        case_sensitive = True
        env_file_encoding = 'utf-8'


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    This ensures we don't read the .env file on every request.
    """
    return Settings()


# Create a settings instance
settings = get_settings()


def is_development() -> bool:
    """Check if we're in development environment."""
    return settings.ENV.lower() == "development"


def is_production() -> bool:
    """Check if we're in production environment."""
    return settings.ENV.lower() == "production"


def is_staging() -> bool:
    """Check if we're in staging environment."""
    return settings.ENV.lower() == "staging"


def get_cors_origins() -> List[str]:
    """Get CORS origins as a list."""
    if isinstance(settings.BACKEND_CORS_ORIGINS, str):
        return [origin.strip() for origin in settings.BACKEND_CORS_ORIGINS.split(",")]
    return settings.BACKEND_CORS_ORIGINS


def get_database_config() -> dict:
    """Get database configuration as a dictionary."""
    return {
        "url": settings.database_url,
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_pre_ping": settings.DB_POOL_PRE_PING,
        "ssl_mode": settings.DB_SSL_MODE,
        "connect_timeout": settings.DB_CONNECT_TIMEOUT,
    }


def get_security_config() -> dict:
    """Get security configuration as a dictionary."""
    return {
        "secret_key": settings.SECRET_KEY,
        "algorithm": settings.ALGORITHM,
        "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        "refresh_token_expire_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
    }


def get_server_config() -> dict:
    """Get server configuration as a dictionary."""
    return {
        "host": settings.server_host,
        "port": settings.server_port,
        "debug": settings.DEBUG,
    }


def get_llm_config() -> dict:
    """Get LLM configuration as a dictionary."""
    return {
        "openai_api_key": settings.OPENAI_API_KEY,
    }


