from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select, delete, update, func, or_, and_
import logging
from database import EventModel
from models import EventCreate, EventUpdate, Event
from datetime import datetime, timedelta
from exceptions import EventNotFoundError, EventPermissionError,  DatabaseError
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class EventAdapter:
    """
    Event adapter for database operations.
    
    This adapter provides async interface for event CRUD operations
    with proper error handling and session management.
    """
    
    def __init__(self, session: AsyncSession):
        self.db: AsyncSession = session
    
    def _convert_to_model(self, event_model: EventModel) -> Event:
        """Convert EventModel to Event Pydantic model."""
        
        
        delta = event_model.endDate - event_model.startDate
        duration = int(delta.total_seconds() / 60)

        
        return Event(
            id=event_model.event_id,
            title=event_model.title,
            startDate=event_model.startDate,
            endDate=event_model.endDate,
            duration=duration,
            location=event_model.location,
            user_id=event_model.user_id,
            priority=event_model.priority,
            flexibility=event_model.flexibility,
            category=event_model.category,
        )
    
    def _convert_to_db_model(self, user_id: int, event_data: EventCreate) -> EventModel:
        """Convert EventCreate Pydantic model to EventModel."""
        
        end_date = None
        if event_data.duration and event_data.duration > 0:
            end_date = event_data.startDate + timedelta(minutes=event_data.duration)
        else:
            end_date = event_data.startDate
            
        return EventModel(
            title=event_data.title,
            startDate=event_data.startDate,
            endDate=end_date,
            location=event_data.location,
            user_id=user_id,
            priority=event_data.priority,
            flexibility=event_data.flexibility,
            category=event_data.category,
        )
    
    def _ensure_datetime(self, value: Optional[datetime | str]) -> Optional[datetime]:
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value
    
    async def create_event(self, user_id: int, event_data: EventCreate) -> Event:
        """
        Create a new event.
        
        Args:
            event_data: Event data to create
            
        Returns:
            Created event
            
        Raises:
            DatabaseError: If there's a database error
        """
        try:
            db_event = self._convert_to_db_model(user_id, event_data)
            self.db.add(db_event)
            await self.db.commit()
            
            logger.info(f"Created event: {db_event.event_id}")
            return self._convert_to_model(db_event)
            
        except SQLAlchemyError as e:
            logger.error(f"Database error creating event: {e}")
            await self.db.rollback()
            raise DatabaseError(f"Failed to create event: {e}")
        except Exception as e:
            logger.error(f"Unexpected error creating event: {e}")
            await self.db.rollback()
            raise DatabaseError(f"Unexpected error creating event: {e}")
        
    async def create_events(self, user_id: int, event_data: List[EventCreate]) -> List[Event]:
        """
        Create multiple events.
        
        Args:
            event_data: List of event data to create
        
        Returns:
            List of created events
            
        Raises:
            DatabaseError: If there's a database error
        """
        try:
            db_events = [self._convert_to_db_model(user_id, event) for event in event_data]
            self.db.add_all(db_events)
            await self.db.commit()
            
            return [self._convert_to_model(db_event) for db_event in db_events] 
        
        except SQLAlchemyError as e:
            logger.error(f"Database error creating events: {e}")
            await self.db.rollback()
            raise DatabaseError(f"Failed to create events: {e}")
        except Exception as e:
            logger.error(f"Unexpected error creating events: {e}")
    
    async def get_event_by_event_id(self, event_id: str) -> Event:
        """
        Get event by event_id (UUID).
        
        Args:
            event_id: Event ID (UUID) to retrieve
            
        Returns:
            Event
            
        Raises:
            EventNotFoundError: If event is not found
            DatabaseError: If there's a database error
        """
        try:
            stmt = select(EventModel).where(EventModel.event_id == event_id)
            result = await self.db.execute(stmt)
            db_event = result.scalar_one_or_none()
            
            if db_event:
                return self._convert_to_model(db_event)
            raise EventNotFoundError(f"Event with ID {event_id} not found")
            
        except EventNotFoundError:
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving event {event_id}: {e}")
            raise DatabaseError(f"Database error retrieving event {event_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error retrieving event {event_id}: {e}")
            raise DatabaseError(f"Unexpected error retrieving event {event_id}: {e}")
         
    async def get_events_by_user_id(self, user_id: int, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Event]:
        """
        Get all events for a specific user with optional pagination.
        
        Args:
            user_id: User ID to filter events
            limit: Maximum number of events to return
            offset: Number of events to skip
            
        Returns:
            List of events
        """
        try:
            stmt = select(EventModel).where(EventModel.user_id == user_id).order_by(EventModel.startDate.desc())
            
            if offset:
                stmt = stmt.offset(offset)
            if limit:
                stmt = stmt.limit(limit)
            
            result = await self.db.execute(stmt)
            db_events = result.scalars().all()
            
                    
            return [self._convert_to_model(event) for event in db_events]
            
        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving events for user {user_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error retrieving events for user {user_id}: {e}")
            return []
    
    async def get_all_events(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[Event]:
        """
        Get all events with optional pagination.
        
        Args:
            limit: Maximum number of events to return
            offset: Number of events to skip
            
        Returns:
            List of events
        """
        try:
            stmt = select(EventModel).order_by(EventModel.startDate.desc())
            
            if offset:
                stmt = stmt.offset(offset)
            if limit:
                stmt = stmt.limit(limit)
            
            result = await self.db.execute(stmt)
            db_events = result.scalars().all()
            return [self._convert_to_model(event) for event in db_events]
            
        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving events: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error retrieving events: {e}")
            return []
    
    async def get_events_by_date_range(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Event]:
        """
        Get events within an optional date range for a specific user.
        
        Args:
            user_id: User ID to filter events
            start_date: Optional start date (YYYY-MM-DD HH:MM:SS)
            end_date: Optional end date (YYYY-MM-DD HH:MM:SS)
            
        Returns:
            List of events filtered by optional date range (empty list if no events found)
            
        Raises:
            DatabaseError: If there's a database error
        """
        try:
            conditions = [EventModel.user_id == user_id]

            if start_date:
                conditions.append(EventModel.startDate >= self._ensure_datetime(start_date))
            if end_date:
                conditions.append(EventModel.endDate <= self._ensure_datetime(end_date))

            stmt = select(EventModel).where(*conditions).order_by(EventModel.startDate.asc())
            
            result = await self.db.execute(stmt)
            db_events = result.scalars().all()
            
            return [self._convert_to_model(event) for event in db_events]

        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving events by date range: {e}")
            raise DatabaseError(f"Database error retrieving events by date range: {e}")
        except Exception as e:
            logger.error(f"Unexpected error retrieving events by date range: {e}")
            raise DatabaseError(f"Unexpected error retrieving events by date range: {e}")

    
    async def update_event(self, event_id: str, user_id: int, event_data: EventUpdate) -> Event:
        """
        Update an existing event.
        
        Args:
            event_id: Event ID (UUID) to update
            user_id: User ID to verify ownership
            event_data: Updated event data
            
        Returns:
            Updated event
            
        Raises:
            EventNotFoundError: If event is not found
            EventPermissionError: If user doesn't have permission
            DatabaseError: If there's a database error
        """
        try:
            # First, get the existing event to verify ownership
            stmt = select(EventModel).where(EventModel.event_id == event_id)
            result = await self.db.execute(stmt)
            db_event = result.scalar_one_or_none()
            
            if not db_event:
                logger.warning(f"Event not found for update: {event_id}")
                raise EventNotFoundError(f"Event with ID {event_id} not found")
            
            if db_event.user_id != user_id:
                logger.warning(f"User {user_id} not authorized to update event {event_id}")
                raise EventPermissionError(f"User {user_id} not authorized to update event {event_id}")
            
            # Update fields
            update_data = {}
            logger.info(f"Processing update fields for event {event_id}")
            logger.info(f"Title: {event_data.title}, StartDate: {event_data.startDate}, Location: {event_data.location}")
            
            if event_data.title is not None:
                update_data['title'] = event_data.title
            if event_data.startDate is not None:
                update_data['startDate'] = event_data.startDate
            if event_data.location is not None:
                update_data['location'] = event_data.location
            if event_data.priority is not None:
                update_data['priority'] = event_data.priority
            if event_data.flexibility is not None:
                update_data['flexibility'] = event_data.flexibility
            if event_data.category is not None:
                update_data['category'] = event_data.category
            
            # Handle endDate and duration logic
            logger.info(f"Update event {event_id}: duration={event_data.duration}, startDate={event_data.startDate}")
            
            if event_data.duration is not None or event_data.startDate is not None:
                start_date = event_data.startDate if event_data.startDate is not None else db_event.startDate
                duration = event_data.duration if event_data.duration is not None else 0
                update_data['endDate'] = start_date + timedelta(minutes=duration)
            
            if update_data:
                stmt = update(EventModel).where(EventModel.event_id == event_id).values(**update_data).returning(EventModel)
                result = await self.db.execute(stmt)
                db_event = result.scalar_one_or_none()
                await self.db.commit()
                logger.info(f"Updated event: {event_id}")
                if db_event:
                    return self._convert_to_model(db_event)
                else:
                    raise DatabaseError(f"Failed to retrieve updated event {event_id}")
            else:
                # No changes to make, return the original event
                return self._convert_to_model(db_event)
                
        except (EventNotFoundError, EventPermissionError, HTTPException):
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error updating event {event_id}: {e}")
            await self.db.rollback()
            raise DatabaseError(f"Database error updating event {event_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error updating event {event_id}: {e}")
            await self.db.rollback()
            raise DatabaseError(f"Unexpected error updating event {event_id}: {e}")
    
    async def delete_event(self, event_id: str, user_id: int) -> bool:
        """
        Delete an event.
        
        Args:
            event_id: Event ID (UUID) to delete
            user_id: User ID to verify ownership
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            stmt = delete(EventModel).where(
                EventModel.event_id == event_id,
                EventModel.user_id == user_id
            )
            result = await self.db.execute(stmt)
            deleted_count = result.rowcount
            
            if deleted_count == 1:
                await self.db.commit()
                logger.info(f"Deleted event: {event_id}")
                return True
            else:
                await self.db.rollback()
                logger.warning(f"Event not found or not authorized for deletion: {event_id}")
                return False
            
        except SQLAlchemyError as e:
            logger.error(f"Database error deleting event {event_id}: {e}")
            await self.db.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting event {event_id}: {e}")
            await self.db.rollback()
            return False
    
    async def search_events(self, user_id: int, query: str) -> List[Event]:
        """
        Search events by title or location for a specific user.
        
        Args:
            user_id: User ID to filter events
            query: Search query
            
        Returns:
            List of matching events
        """
        try:
            search_term = f"%{query}%"
            stmt = select(EventModel).where(
                EventModel.user_id == user_id,
                (EventModel.title.ilike(search_term) | EventModel.location.ilike(search_term))
            ).order_by(EventModel.startDate.desc())
            
            result = await self.db.execute(stmt)
            db_events = result.scalars().all()
            
            return [self._convert_to_model(event) for event in db_events]
            
        except SQLAlchemyError as e:
            logger.error(f"Database error searching events: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error searching events: {e}")
            return []
    
    async def get_events_count(self, user_id: int) -> int:
        """
        Get the count of events for a specific user.
        
        Args:
            user_id: User ID to filter events
            
        Returns:
            Number of events
        """
        try:
            stmt = select(func.count(EventModel.id)).where(EventModel.user_id == user_id)
            result = await self.db.execute(stmt)
            count = result.scalar()
            
            return count or 0
            
        except SQLAlchemyError as e:
            logger.error(f"Database error counting events: {e}")
            return 0
        except Exception as e:
            logger.error(f"Unexpected error counting events: {e}")
            return 0

    async def check_event_conflict(
        self,
        user_id: int,
        start_date: datetime,
        end_date: datetime,
        exclude_event_id: Optional[str] = None
    ) -> Optional[Event]:
        """
        Check if there's an event that conflicts with the given date range.
        
        Args:
            user_id: User ID to filter events
            start_date: Start date of the time range to check
            end_date: End date of the time range to check
            exclude_event_id: Optional event ID to exclude from conflict check (useful for updates)
            
        Returns:
            Conflicting event if found, None if no conflicts
        """
        try:
            conditions = [
            EventModel.user_id == user_id,
            or_(
                and_(
                    EventModel.startDate < self._ensure_datetime(end_date),
                    EventModel.endDate > self._ensure_datetime(start_date)
                ),
                and_(
                    EventModel.startDate == self._ensure_datetime(start_date),
                    EventModel.endDate == self._ensure_datetime(end_date)
                )
            )
            ]
            # Exclude a specific event (useful when updating an event)
            if exclude_event_id:
                conditions.append(EventModel.event_id != exclude_event_id)
            
            stmt = select(EventModel).where(*conditions).limit(1)
            result = await self.db.execute(stmt)
            conflicting_event = result.scalar_one_or_none()
            
            if conflicting_event:
                logger.info(f"Found conflicting event: {conflicting_event.event_id} for time range {start_date} - {end_date}")
                return self._convert_to_model(conflicting_event)
            
            return None
            
        except SQLAlchemyError as e:
            logger.error(f"Database error checking event conflicts: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error checking event conflicts: {e}")
            return None

    async def delete_multiple_events(self, event_ids: List[str], user_id: int) -> bool:
        """
        Delete multiple events by their IDs.
        
        Args:
            event_ids: List of event IDs (UUIDs) to delete
            user_id: User ID to verify ownership
            
        Returns:
            True if ALL events were successfully deleted, False if ANY failed (none deleted)
        """
        try:
            stmt = delete(EventModel).where(
                EventModel.event_id.in_(event_ids),
                EventModel.user_id == user_id
            )
            result = await self.db.execute(stmt)
            deleted_count = result.rowcount
            
            if deleted_count == len(event_ids):
                await self.db.commit()
                logger.info(f"Successfully deleted {deleted_count} events")
                return True
            else:
                await self.db.rollback()
                logger.warning(f"Only {deleted_count} out of {len(event_ids)} events were deleted")
                return False
            
        except SQLAlchemyError as e:
            logger.error(f"Database error in bulk delete operation: {e}")
            await self.db.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error in bulk delete operation: {e}")
            await self.db.rollback()
            return False
