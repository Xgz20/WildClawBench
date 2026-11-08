"""Exact historical prompt templates remain readable without accepting edits."""
import unittest
from tests.general_e2e.test_general_scoring_orchestration import ORCHESTRATOR


class HistoricalPromptRenderingTests(unittest.TestCase):
    def test_current_and_exact_pre_notice_template_match(self):
        marker=ORCHESTRATOR.PRESENTATION_ADMISSION_NOTICE+'\n\n'
        current='frozen identity\n\n'+marker+'frozen rubric and model'
        legacy='frozen identity\n\nfrozen rubric and model'
        self.assertTrue(ORCHESTRATOR._prompt_matches_known_rendering(current,current))
        self.assertTrue(ORCHESTRATOR._prompt_matches_known_rendering(legacy,current))

    def test_identity_model_or_spacing_changes_are_rejected(self):
        current='gpt-6.1-sol/high\n\n'+ORCHESTRATOR.PRESENTATION_ADMISSION_NOTICE+'\n\nrubric'
        legacy='gpt-6.1-sol/high\n\nrubric'
        for edited in [legacy.replace('high','low'),legacy+'\n',legacy.replace('rubric','changed')]:
            self.assertFalse(ORCHESTRATOR._prompt_matches_known_rendering(edited,current))

    def test_unrelated_or_duplicate_marker_cannot_define_a_legacy_form(self):
        marker=ORCHESTRATOR.PRESENTATION_ADMISSION_NOTICE+'\n\n'
        self.assertFalse(ORCHESTRATOR._prompt_matches_known_rendering('identity','identity\n'))
        self.assertFalse(ORCHESTRATOR._prompt_matches_known_rendering('identity',marker+marker+'identity'))


if __name__=='__main__':unittest.main()
