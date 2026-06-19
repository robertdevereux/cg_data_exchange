from django.db import models


class IHTReckoner(models.Model):
    """
    Stores the computed threshold question and answer for an IHT case.
    One row per case — created or updated when the executor completes
    the reckoner and answers the threshold question.

    conclusion values:
      'not_payable'    — estate below threshold, IHT not payable
      'may_be_payable' — estate at or above threshold, IHT may be payable
      'knock_out'      — disqualifying circumstances, must use main flow
    """
    case           = models.OneToOneField(
                         'core.Case',
                         on_delete=models.CASCADE,
                         related_name='iht_reckoner',
                     )
    conclusion     = models.CharField(max_length=20)
    question_text  = models.TextField(blank=True, default='')
    threshold      = models.IntegerField(null=True, blank=True)
    answer         = models.CharField(max_length=10, blank=True, default='')
    answered_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dept_hmrc_ihtreckoner'

    def __str__(self):
        return f"IHTReckoner({self.case_id}, {self.conclusion})"
