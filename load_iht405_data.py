from django.core.management.base import BaseCommand
from core.models import Question, Section, Routing, Regime, Schedule


class Command(BaseCommand):
    help = "Load IHT405 questions, sections and routing"

    def handle(self, *args, **options):
        regime = Regime.objects.get(regime_id="HMRC_IHT")

        # ── Questions ──────────────────────────────────────────────────────

        q_HMRC_H1, _ = Question.objects.update_or_create(
            question_id='HMRC_H1',
            defaults=dict(
                question_text='Name of the deceased',
                question_type='personal_name',
                guidance=None,
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_H2, _ = Question.objects.update_or_create(
            question_id='HMRC_H2',
            defaults=dict(
                question_text='Date of death',
                question_type='date',
                guidance=None,
                hint='For example, 31 3 2025',
                options=None,
                answer_type='date',
                is_platform=False,
            )
        )

        q_HMRC_N1, _ = Question.objects.update_or_create(
            question_id='HMRC_N1',
            defaults=dict(
                question_text='Is the valuation contact different from the person named on form IHT400, box 17?',
                question_type='radio',
                guidance='Only complete the valuation contact section if the person we should contact about the valuation of houses or land is different from the one named on form IHT400, box 17. Make sure they have the legal personal representative\'s authority to be contacted.',
                hint=None,
                options='Yes;No',
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_1, _ = Question.objects.update_or_create(
            question_id='HMRC_1',
            defaults=dict(
                question_text='What is the name of the firm or person dealing with the valuation of the houses or land?',
                question_type='text',
                guidance=None,
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_2, _ = Question.objects.update_or_create(
            question_id='HMRC_2',
            defaults=dict(
                question_text='What is the address of the firm or person dealing with the valuation of the houses or land?',
                question_type='address',
                guidance=None,
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_3, _ = Question.objects.update_or_create(
            question_id='HMRC_3',
            defaults=dict(
                question_text='Contact name, if different from box 1',
                question_type='text',
                guidance=None,
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_4, _ = Question.objects.update_or_create(
            question_id='HMRC_4',
            defaults=dict(
                question_text='What is the title of the contact?',
                question_type='text',
                guidance=None,
                hint='For example, Mr, Mrs, Miss, Ms or other title',
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_5, _ = Question.objects.update_or_create(
            question_id='HMRC_5',
            defaults=dict(
                question_text='What is the phone number for the valuation contact?',
                question_type='text',
                guidance=None,
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_6, _ = Question.objects.update_or_create(
            question_id='HMRC_6',
            defaults=dict(
                question_text='What is the DX number and town for the valuation contact (if used)?',
                question_type='text',
                guidance=None,
                hint='Only complete if a DX number is used',
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_7, _ = Question.objects.update_or_create(
            question_id='HMRC_7',
            defaults=dict(
                question_text="What is the contact's reference?",
                question_type='text',
                guidance=None,
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_8, _ = Question.objects.update_or_create(
            question_id='HMRC_8',
            defaults=dict(
                question_text='Item number',
                question_type='number',
                guidance='Number each item of property.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_9, _ = Question.objects.update_or_create(
            question_id='HMRC_9',
            defaults=dict(
                question_text='Full address or description of property',
                question_type='textarea',
                guidance='Give the full address or description of the property. If the property has no street number, or it is farmland or other land without an address, enclose a plan that clearly shows the boundaries of the property.',
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_10, _ = Question.objects.update_or_create(
            question_id='HMRC_10',
            defaults=dict(
                question_text='Postcode of property',
                question_type='text',
                guidance=None,
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_N2, _ = Question.objects.update_or_create(
            question_id='HMRC_N2',
            defaults=dict(
                question_text='Is this property freehold or leasehold?',
                question_type='radio_inline',
                guidance='State whether the deceased owned the property outright (freehold) or had a lease (leasehold).',
                hint=None,
                options='Freehold;Leasehold',
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_11, _ = Question.objects.update_or_create(
            question_id='HMRC_11',
            defaults=dict(
                question_text='Length of lease (years remaining)',
                question_type='number',
                guidance=None,
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_12, _ = Question.objects.update_or_create(
            question_id='HMRC_12',
            defaults=dict(
                question_text='Annual ground rent',
                question_type='number',
                guidance=None,
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_13, _ = Question.objects.update_or_create(
            question_id='HMRC_13',
            defaults=dict(
                question_text='Details of lettings/leases',
                question_type='textarea',
                guidance="If the property was let out by the deceased, provide a copy of the lease, sublease, business or agricultural tenancy agreement. If the following information is not in the agreement, or there is no written agreement, enter it here: date the tenancy or lease began; date the tenancy is due to end; what rent is payable and whether it can be reviewed; who is responsible for the outgoings on the property; name of the tenant. If the property was unoccupied at the date of death, write 'vacant'.",
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_14, _ = Question.objects.update_or_create(
            question_id='HMRC_14',
            defaults=dict(
                question_text='Value of Agricultural or Business Relief at 100% or Woodlands Relief or heritage exemption deducted',
                question_type='number',
                guidance='If you are deducting Agricultural Relief, Woodlands Relief, Business Relief or claiming heritage exemption, enter the value of the property that qualifies for relief or exemption. You cannot deduct Business Relief on businesses that deal in properties or investments. For deaths on and after 6 April 2026, relief at 100% on the combined value of qualifying agricultural and/or business property is limited to \u00a32.5 million.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_15, _ = Question.objects.update_or_create(
            question_id='HMRC_15',
            defaults=dict(
                question_text='Value of Agricultural or Business Relief at 50%',
                question_type='number',
                guidance='Where the total value of qualifying property exceeds \u00a32.5 million, the excess qualifies for relief at 50%. Unused \u00a32.5 million allowance from a late spouse or civil partner may be transferred to the deceased\'s estate, provided a claim is made within 4 years of the survivor\'s death or within 6 months of the personal representatives starting their role.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_16, _ = Question.objects.update_or_create(
            question_id='HMRC_16',
            defaults=dict(
                question_text='Open market value at date of death',
                question_type='number',
                guidance='Enter the open market value of the property at the date of death. Copy the total of this column to form IHT400, box 51.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_17, _ = Question.objects.update_or_create(
            question_id='HMRC_17',
            defaults=dict(
                question_text='Item number',
                question_type='number',
                guidance='Number each item of property.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_18, _ = Question.objects.update_or_create(
            question_id='HMRC_18',
            defaults=dict(
                question_text='Full address or description of property',
                question_type='textarea',
                guidance='Give the full address or description of the property. For rights over land (such as fishing or mineral rights) give details of those rights as well as details of the land. If the property has no street number, or it is farmland or other land without an address, enclose a plan that clearly shows the boundaries of the property.',
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_19, _ = Question.objects.update_or_create(
            question_id='HMRC_19',
            defaults=dict(
                question_text='Postcode of property',
                question_type='text',
                guidance=None,
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_N3, _ = Question.objects.update_or_create(
            question_id='HMRC_N3',
            defaults=dict(
                question_text='Is this property freehold or leasehold?',
                question_type='radio_inline',
                guidance='State whether the deceased owned the property outright (freehold) or had a lease (leasehold).',
                hint=None,
                options='Freehold;Leasehold',
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_20, _ = Question.objects.update_or_create(
            question_id='HMRC_20',
            defaults=dict(
                question_text='Length of lease (years remaining)',
                question_type='number',
                guidance=None,
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_21, _ = Question.objects.update_or_create(
            question_id='HMRC_21',
            defaults=dict(
                question_text='Annual ground rent',
                question_type='number',
                guidance=None,
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_22, _ = Question.objects.update_or_create(
            question_id='HMRC_22',
            defaults=dict(
                question_text='Details of lettings/leases',
                question_type='textarea',
                guidance="If the property was let out by the deceased, provide a copy of the lease, sublease, business or agricultural tenancy agreement. If the following information is not in the agreement, or there is no written agreement, enter it here: date the tenancy or lease began; date the tenancy is due to end; what rent is payable and whether it can be reviewed; who is responsible for the outgoings on the property; name of the tenant. If the property was unoccupied at the date of death, write 'vacant'.",
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_23, _ = Question.objects.update_or_create(
            question_id='HMRC_23',
            defaults=dict(
                question_text='Value of Agricultural or Business Relief at 100% or Woodlands Relief or heritage exemption deducted',
                question_type='number',
                guidance='If you are deducting Agricultural Relief, Woodlands Relief, Business Relief or claiming heritage exemption, enter the value of the property that qualifies for relief or exemption. You cannot deduct Business Relief on businesses that deal in properties or investments. For deaths on and after 6 April 2026, relief at 100% on the combined value of qualifying agricultural and/or business property is limited to \u00a32.5 million.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_24, _ = Question.objects.update_or_create(
            question_id='HMRC_24',
            defaults=dict(
                question_text='Value of Agricultural or Business Relief at 50%',
                question_type='number',
                guidance='Where the total value of qualifying property exceeds \u00a32.5 million, the excess qualifies for relief at 50%.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_25, _ = Question.objects.update_or_create(
            question_id='HMRC_25',
            defaults=dict(
                question_text='Open market value at date of death',
                question_type='number',
                guidance='Enter the open market value of the property at the date of death. Include this amount in form IHT400, boxes 68 to 70.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_N4, _ = Question.objects.update_or_create(
            question_id='HMRC_N4',
            defaults=dict(
                question_text='Were any of the properties listed on this form subject to special factors that may affect their value?',
                question_type='radio',
                guidance='Special factors include things such as major damage or development potential. If a property is damaged in a way that is covered by building insurance, it may affect how we value it. If Yes, give details using the same item numbers used in the property details section.',
                hint=None,
                options='Yes;No',
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_26, _ = Question.objects.update_or_create(
            question_id='HMRC_26',
            defaults=dict(
                question_text='Item number',
                question_type='number',
                guidance='Use the same item numbers used in the property details section.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_27, _ = Question.objects.update_or_create(
            question_id='HMRC_27',
            defaults=dict(
                question_text='Details of the special factors',
                question_type='textarea',
                guidance="Enclose a copy of the survey or structural engineer's report, or planning approval notice if appropriate.",
                hint=None,
                options=None,
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_N5, _ = Question.objects.update_or_create(
            question_id='HMRC_N5',
            defaults=dict(
                question_text='Was the property damaged?',
                question_type='radio',
                guidance="If the property was damaged, answer Yes to indicate whether the deceased's insurance covered all or part of the repairs.",
                hint=None,
                options='Yes;No',
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_N6, _ = Question.objects.update_or_create(
            question_id='HMRC_N6',
            defaults=dict(
                question_text="Did the deceased's insurance cover all or part of the repairs?",
                question_type='radio',
                guidance=None,
                hint=None,
                options='Yes;No',
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_28, _ = Question.objects.update_or_create(
            question_id='HMRC_28',
            defaults=dict(
                question_text="Do you intend to make a claim under the deceased's insurance policy?",
                question_type='radio',
                guidance='If Yes, attach copies of any correspondence you have had with the insurers or loss adjusters.',
                hint=None,
                options='Yes;No',
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_N7, _ = Question.objects.update_or_create(
            question_id='HMRC_N7',
            defaults=dict(
                question_text='Have any of the properties been sold, or do you intend to sell any of them within 12 months of the date of death?',
                question_type='radio',
                guidance='If Yes, give details using the same item numbers used in the property details section.',
                hint=None,
                options='Yes;No',
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_29, _ = Question.objects.update_or_create(
            question_id='HMRC_29',
            defaults=dict(
                question_text='Item number',
                question_type='number',
                guidance='Use the same item numbers used in the property details section.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_30, _ = Question.objects.update_or_create(
            question_id='HMRC_30',
            defaults=dict(
                question_text='Sale status and date contracts were exchanged (if sold)',
                question_type='radio_inline',
                guidance='If the property has been sold, give the date contracts were exchanged (or missives concluded for property in Scotland).',
                hint=None,
                options='Already been sold;Is on the market now;Will be sold later',
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_31, _ = Question.objects.update_or_create(
            question_id='HMRC_31',
            defaults=dict(
                question_text='Asking price or agreed sale price',
                question_type='number',
                guidance='Do not deduct the costs of the sale.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_32, _ = Question.objects.update_or_create(
            question_id='HMRC_32',
            defaults=dict(
                question_text='Was the sale to a relative, friend or business colleague of the deceased?',
                question_type='radio_inline',
                guidance=None,
                hint=None,
                options='Yes;No',
                answer_type='text',
                is_platform=False,
            )
        )

        q_HMRC_33, _ = Question.objects.update_or_create(
            question_id='HMRC_33',
            defaults=dict(
                question_text='Price for fixtures, carpets and curtains, if included in sale price',
                question_type='number',
                guidance='Only complete if the price for fixtures, carpets and curtains is included in the sale price.',
                hint=None,
                options=None,
                answer_type='number',
                is_platform=False,
            )
        )

        q_HMRC_34, _ = Question.objects.update_or_create(
            question_id='HMRC_34',
            defaults=dict(
                question_text='Do you want to use the sale price as the value at the date of death?',
                question_type='radio_inline',
                guidance=None,
                hint=None,
                options='Yes;No',
                answer_type='text',
                is_platform=False,
            )
        )

        self.stdout.write(self.style.SUCCESS('Done.'))