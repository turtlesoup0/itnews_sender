"""
수신인 관리 모듈
"""
from .recipient_manager import RecipientManager, get_active_recipients, unsubscribe_recipient
from .models import Recipient, RecipientStatus

__all__ = ["RecipientManager", "Recipient", "RecipientStatus", "get_active_recipients", "unsubscribe_recipient"]
