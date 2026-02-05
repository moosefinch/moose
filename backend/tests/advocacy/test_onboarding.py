"""Tests for FamilyOnboarding."""

import pytest

from advocacy.onboarding import FamilyOnboarding, OnboardingStage


class TestOnboardingFlow:
    def test_initial_state(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        assert ob.stage == OnboardingStage.INTRO
        assert ob.is_complete is False
        assert ob.is_started is False

    def test_start(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        prompt = ob.start()
        assert ob.is_started is True
        assert "optional" in prompt.lower()

    def test_skip_at_intro(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        ob.start()
        result = ob.process_response("no")
        assert result["complete"] is True
        assert ob.is_complete is True

    def test_full_flow_solo(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        ob.start()

        # Intro
        result = ob.process_response("yes")
        assert result["stage"] == OnboardingStage.ABOUT_YOU

        # About you
        result = ob.process_response("I'm Alex, a software developer")
        assert result["stage"] == OnboardingStage.GOALS

        # Goals
        result = ob.process_response("Get fit\nLearn piano\nSave for a house")
        assert result["stage"] == OnboardingStage.ADVOCATES

        # No advocates
        result = ob.process_response("no")
        assert result["stage"] == OnboardingStage.FAMILY

        # No family
        result = ob.process_response("just me")
        assert result["complete"] is True

    def test_flow_with_advocate(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        ob.start()
        ob.process_response("yes")  # intro
        ob.process_response("Alex")  # about
        ob.process_response("Fitness")  # goals

        # Add advocate
        result = ob.process_response("Sarah")
        assert result["stage"] == OnboardingStage.ADVOCATE_DETAILS

        # Advocate details
        result = ob.process_response("email, health and finances")
        assert result["stage"] == OnboardingStage.FAMILY

        # No family
        result = ob.process_response("no")
        assert result["complete"] is True

    def test_flow_with_family(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        ob.start()
        ob.process_response("yes")
        ob.process_response("Alex")
        ob.process_response("Goals")
        ob.process_response("no")  # no advocates

        # Add family
        result = ob.process_response("Emma")
        assert result["stage"] == OnboardingStage.FAMILY_MEMBER

        # Family member details
        result = ob.process_response("She's 10 years old")
        assert result["complete"] is True

    def test_multiple_advocates(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        ob.start()
        ob.process_response("yes")
        ob.process_response("Alex")
        ob.process_response("Goals")

        # Multiple advocates
        result = ob.process_response("Sarah, Dr. Smith")
        assert result["stage"] == OnboardingStage.ADVOCATE_DETAILS

        # First advocate details
        result = ob.process_response("email, health")
        assert result["stage"] == OnboardingStage.ADVOCATE_DETAILS

        # Second advocate details
        result = ob.process_response("email, mental health")
        assert result["stage"] == OnboardingStage.FAMILY

    def test_multiple_family_members(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        ob.start()
        ob.process_response("yes")
        ob.process_response("Parent")
        ob.process_response("Goals")
        ob.process_response("no")  # advocates

        result = ob.process_response("Emma, Jake")
        assert result["stage"] == OnboardingStage.FAMILY_MEMBER

        result = ob.process_response("She's 10")
        assert result["stage"] == OnboardingStage.FAMILY_MEMBER

        result = ob.process_response("He's 14")
        assert result["complete"] is True


class TestPersistence:
    def test_state_persists(self, onboarding_path):
        ob1 = FamilyOnboarding(onboarding_path)
        ob1.start()
        ob1.process_response("yes")
        ob1.process_response("Alex")

        ob2 = FamilyOnboarding(onboarding_path)
        assert ob2.stage == OnboardingStage.GOALS
        assert ob2.is_started is True

    def test_reset(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        ob.start()
        ob.process_response("yes")
        ob.process_response("Alex")
        ob.reset()
        assert ob.stage == OnboardingStage.INTRO
        assert ob.is_started is False


class TestDataCollection:
    def test_collected_data(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        ob.start()
        ob.process_response("yes")
        ob.process_response("Alex, developer")
        ob.process_response("Fitness, Piano, Savings")
        ob.process_response("Sarah")
        ob.process_response("email, health")
        ob.process_response("no")

        data = ob.get_collected_data()
        assert data["user"]["raw_response"] == "Alex, developer"
        assert len(data["goals"]) == 3
        assert "Fitness" in data["goals"]
        assert len(data["advocates"]) == 1
        assert data["advocates"][0]["name"] == "Sarah"

    def test_age_extraction(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        ob.start()
        ob.process_response("yes")
        ob.process_response("Parent")
        ob.process_response("Goals")
        ob.process_response("no")
        ob.process_response("Emma")
        ob.process_response("She's 10 years old")

        data = ob.get_collected_data()
        assert data["family"][0].get("age") == 10


class TestStatus:
    def test_get_status(self, onboarding_path):
        ob = FamilyOnboarding(onboarding_path)
        status = ob.get_status()
        assert status["stage"] == OnboardingStage.INTRO
        assert status["started"] is False
        assert status["complete"] is False
