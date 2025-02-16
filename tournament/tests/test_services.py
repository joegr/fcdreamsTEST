
from django.test import TestCase
from ..services.group_stage import GroupStageService
from ..services.knockout import KnockoutService

class ServiceTests(TestCase):
    """Test service layer functionality"""
    # Move service-specific tests here