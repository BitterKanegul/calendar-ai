import logging
from fastapi import HTTPException, Depends
from services.event_service import get_event_service, EventService
from utils.jwt import get_user_id_from_token
from langchain_core.messages import HumanMessage
from flow.builder import FlowBuilder
from models import (
    SuccessfulListResponse, SuccessfulDeleteResponse, SuccessfulCreateResponse,
    SuccessfulUpdateResponse, SuccessfulConflictResolutionResponse,
    SuccessfulPlanResponse, EmailExtractionResponse, ExtractedEmailEvent,
    ConflictResolutionOption, PlanChange, EventCreate, ConfirmationRequiredResponse,
    LeisureSearchResponse, LeisureEvent,
)
from langchain_core.runnables import RunnableConfig
logger = logging.getLogger(__name__)



class AssistantService:

    def __init__(self, event_service: EventService):
        self.event_service = event_service

    async def process(self, token: str, text: str, current_datetime: str, weekday: str, days_in_month: int):
        try:            
            user_id = get_user_id_from_token(token)
            flow = await FlowBuilder().create_flow()
            config: RunnableConfig = {'thread_id': user_id}
            
            response = await flow.ainvoke({
                "user_id": user_id, 
                "router_messages": [HumanMessage(content=text)], 
                "input_text": text,
                "current_datetime": current_datetime, 
                "weekday": weekday, 
                "days_in_month": days_in_month
            }, config=config)
            
            route = response.get("route", {}).get('route') if isinstance(response.get("route"), dict) else None
            is_success = response.get("is_success", False)
            
        
            if is_success:
                # Conflict resolution takes priority — user chose from options or needs to choose
                if response.get("awaiting_confirmation") and response.get("resolution_plan"):
                    resolution_plan = response["resolution_plan"]
                    options = [
                        ConflictResolutionOption(
                            option_num=opt["option_num"],
                            description=opt["description"],
                            action=opt["action"],
                        )
                        for opt in resolution_plan.get("options", [])
                    ]
                    message = response["create_messages"][-1].content if response.get("create_messages") else "Please choose an option."
                    return SuccessfulConflictResolutionResponse(
                        message=message,
                        options=options,
                    ).model_dump()

                # Safety gate: pending delete or update confirmation
                conf_type = response.get("confirmation_type")
                if response.get("awaiting_confirmation") and conf_type in ("delete_safety", "update_safety"):
                    if conf_type == "delete_safety":
                        msg_arr = response.get("delete_messages") or []
                    else:
                        msg_arr = response.get("update_messages") or []
                    message = msg_arr[-1].content if msg_arr else "Please confirm this operation."
                    events = (
                        response.get("delete_final_filtered_events", [])
                        if conf_type == "delete_safety"
                        else response.get("update_final_filtered_events", [])
                    )
                    return ConfirmationRequiredResponse(
                        message=message,
                        confirmation_type=conf_type,
                        events=events or [],
                    ).model_dump()

                # Safety confirmation executed — return plain text result
                if conf_type in ("delete_safety", "update_safety") and not response.get("awaiting_confirmation"):
                    if conf_type == "delete_safety":
                        msg_arr = response.get("delete_messages") or []
                    else:
                        msg_arr = response.get("update_messages") or []
                    message = msg_arr[-1].content if msg_arr else "Done."
                    return {"type": "text", "message": message}

                if response.get("leisure_recommended_events") is not None:
                    events_raw = response["leisure_recommended_events"]
                    leisure_events = [
                        LeisureEvent(
                            external_id=ev.get("external_id", ""),
                            title=ev.get("title", ""),
                            description=ev.get("description"),
                            start_date=ev.get("start_date"),
                            end_date=ev.get("end_date"),
                            duration=ev.get("duration"),
                            venue_name=ev.get("venue_name"),
                            venue_address=ev.get("venue_address"),
                            city=ev.get("city"),
                            category=ev.get("category"),
                            price_range=ev.get("price_range"),
                            url=ev.get("url"),
                            image_url=ev.get("image_url"),
                            fits_free_time=ev.get("fits_free_time", False),
                        )
                        for ev in events_raw
                    ]
                    message = response["leisure_messages"][-1].content if response.get("leisure_messages") else "Here are the events I found."
                    return LeisureSearchResponse(
                        message=message,
                        events=leisure_events,
                    ).model_dump()

                if response.get("email_extracted_events") is not None:
                    extracted = response["email_extracted_events"]

                    def _to_model(ev: dict) -> ExtractedEmailEvent:
                        return ExtractedEmailEvent(
                            title=ev.get("title", ""),
                            start_date=ev.get("start_date"),
                            end_date=ev.get("end_date"),
                            location=ev.get("location"),
                            confidence=ev.get("confidence", "low"),
                            source_type=ev.get("source_type"),
                            evidence=ev.get("evidence"),
                        )

                    message = response["email_messages"][-1].content if response.get("email_messages") else "Here's what I found in your emails."
                    return EmailExtractionResponse(
                        message=message,
                        high_confidence=[_to_model(e) for e in extracted.get("high", [])],
                        medium_confidence=[_to_model(e) for e in extracted.get("medium", [])],
                        low_confidence=[_to_model(e) for e in extracted.get("low", [])],
                    ).model_dump()

                if response.get("is_planning_mode"):
                    changes = [
                        PlanChange(
                            action=ch.get("action", "processed"),
                            event_title=ch.get("event", {}).get("title"),
                            event_start=ch.get("event", {}).get("startDate"),
                            detail=ch.get("detail"),
                        )
                        for ch in (response.get("plan_results") or [])
                    ]
                    message = response.get("plan_summary") or (
                        response["create_messages"][-1].content if response.get("create_messages") else "Plan complete."
                    )
                    return SuccessfulPlanResponse(message=message, changes=changes).model_dump()

                if route == "create":
                    create_event_data = response["create_event_data"]
                    events = [EventCreate(
                        title=event_data.get("arguments").get("title"),
                        startDate=event_data.get("arguments").get("startDate"),
                        duration=event_data.get("arguments", {}).get("duration"),
                        location=event_data.get("arguments", {}).get("location"),
                        priority=event_data.get("arguments", {}).get("priority", "optional"),
                        flexibility=event_data.get("arguments", {}).get("flexibility", "movable"),
                        category=event_data.get("arguments", {}).get("category", "personal"),
                    ) for event_data in create_event_data]
                    
                    # Safety check for empty messages array
                    message = response["create_messages"][-1].content if response.get("create_messages") else "Events created successfully"
                    
                    create_response = SuccessfulCreateResponse(
                        message=message, 
                        events=events,
                        conflict_events=response["create_conflict_events"]
                    )
                    return create_response.model_dump()
                elif route == "update":
                    # Safety check for empty messages array
                    message = response["update_messages"][-1].content if response.get("update_messages") else "Events updated successfully"
                    
                    update_response = SuccessfulUpdateResponse(
                        message=message, 
                        events=response["update_final_filtered_events"],
                        update_arguments=response["update_arguments"],
                        update_conflict_event=response["update_conflict_event"]
                    )
                    return update_response.model_dump()
                elif route == "delete":
                    # Safety check for empty messages array
                    message = response["delete_messages"][-1].content if response.get("delete_messages") else "Events deleted successfully"
                    
                    delete_response = SuccessfulDeleteResponse(
                        message=message, 
                        events=response["delete_final_filtered_events"]
                    )
                    return delete_response.model_dump()
                elif route == "list":
                    # Safety check for empty messages array
                    message = response["list_messages"][-1].content if response.get("list_messages") else "Events listed successfully"
                    
                    list_response = SuccessfulListResponse(
                        message=message, 
                        events=response["list_final_filtered_events"]
                    )
                    return list_response.model_dump()
                elif route == "confirmation":
                    # Events created/updated via MCP inside confirmation_handler
                    message = response["create_messages"][-1].content if response.get("create_messages") else "Done!"
                    return {"type": "text", "message": message}
                else:
                    # Safety check for empty messages array
                    message = response["router_messages"][-1].content if response.get("router_messages") else "Request processed"
                    return {"message": message}
            else:
                # Safety check for empty messages array
                message = response["router_messages"][-1].content if response.get("router_messages") else "Request could not be processed"
                return {"message": message}
        except HTTPException as e:
            raise
        except Exception as e:
            logger.error(f"Error in process: {e}")
            raise


def get_assistant_service(
        event_service: EventService = Depends(get_event_service),
) -> AssistantService:
    return AssistantService(event_service)
