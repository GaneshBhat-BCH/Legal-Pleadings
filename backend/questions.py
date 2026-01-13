QUESTIONS_DATA = {
  "role": "You are a Legal & Compliance AI Agent specialized in Conflict of Interest (COI) analysis. You must perform strict rule-based legal evaluation using only the provided REFERENCE_POLICIES. No assumptions, inference, or hallucination are allowed.",

  "QUESTIONS_DATA": {
    "global_instructions": {
      "output_only_value": True,
      "no_explanations": True,
      "multiple_values_format": "Ans1,Ans2",
      "missing_value": "NA",
      "yes_no_values": ["Yes", "No"],
      "rules_reference_instruction": "For questions 13, 14, and 15, perform a deep legal analysis using ONLY the rules defined in REFERENCE_POLICIES. Do not hallucinate."
    },

    "QUESTIONS": [
      {
        "id": 1,
        "text": "Is the researcher a cofounder in a company outside of BCH?",
        "prompt": "Extract the data from the input and determine whether the researcher is a cofounder in a company outside of BCH. Output Yes or No. If not mentioned, return No."
      },
      {
        "id": 2,
        "text": "What is the researcher’s role(s)/title(s) in the company?",
        "prompt": "Extract the data from the input and identify the researcher’s role(s) or title(s) in the company. If multiple roles exist, return Ans1,Ans2. If not mentioned, return NA."
      },
      {
        "id": 3,
        "text": "Is the company publicly traded or privately held?",
        "prompt": "Extract the data from the input and determine whether the company is publicly traded or privately held. Output Public or Private. If not mentioned, return NA."
      },
      {
        "id": 4,
        "text": "What is the researcher’s equity in the company?",
        "prompt": "Extract the data from the input and identify the researcher’s equity in the company. Normalize to Cash,Stock,StockOptions. If multiple, return Ans1,Ans2. If not mentioned, return NA."
      },
      {
        "id": 5,
        "text": "How much will the researcher be compensated in cash from the company annually?",
        "prompt": "Extract the data from the input and identify the annual cash compensation. The result should be ≤ $ 25000 or > $ 25000. If there are no details, return NA."
      },
      {
        "id": 6,
        "text": "How much time/effort does the researcher spend working for the company?",
        "prompt": "Extract the data from the input and identify time or effort spent working for the company. Convert to percentage of FTE. Full-time = 40 hours/week. (Hours / 40) * 100. If >20 return '> 20 %'. If ≤20 return '≤ 20 %'. Return ONLY these values. If not mentioned, return NA."
      },
      {
        "id": 7,
        "text": "Has the company licensed or is it planning to license intellectual property from BCH?",
        "prompt": "Extract the data from the input and determine whether the company has licensed or plans to license intellectual property from BCH. Output Yes or No. If not mentioned, return NA."
      },
      {
        "id": 8,
        "text": "Will BCH receive equity or financial consideration from the company? If so, how much?",
        "prompt": "Extract the data from the input and determine if BCH receives equity ownership percentage, cash payments, milestones, or royalties. Do NOT include costs. If none or not mentioned, return NA."
      },
      {
        "id": 9,
        "text": "Does the researcher have any grants or research projects that relate to the company?",
        "prompt": "Extract the data from the input and determine whether related grants or research projects exist. Output Yes or No. If not mentioned, return NA."
      },
      {
        "id": 10,
        "text": "Is the related research clinical or basic?",
        "prompt": "Extract the data from the input and determine whether the research is Clinical or Basic. If not mentioned, return NA."
      },
      {
        "id": 11,
        "text": "Is the researcher participating in clinical research related to the company’s technology?",
        "prompt": "Extract the data from the input and determine participation in clinical research related to company technology. Output Yes or No. If not mentioned, return NA."
      },
      {
        "id": 12,
        "text": "Is the company seeking to sponsor research at BCH?",
        "prompt": "Extract the data from the input and determine whether the company seeks to sponsor research at BCH. Output Yes or No. If not mentioned, return NA."
      },
      {
        "id": 13,
        "text": "What COI policy applies to this management plan?",
        "prompt": "Perform a DEEP LEGAL ANALYSIS using ONLY REFERENCE_POLICIES. Review answers from Questions 1–12. PRIORITY CHECK: Check FIRST if the researcher is an inventor or co-inventor. If YES, you MUST evaluate against 'Inventor_Equity_and_Licensing_Conflict_Policy' FIRST. If it matches, return that policy. Only if that specific policy does NOT match (or if not an inventor), then proceed to evaluate HMS_COI_Policy, PHS_COI_Policy, or BCH_COI_Policy. If a policy is not immediately clear, you MUST RE-READ the RAW INPUT TEXT. Return 'NA' only if absolutely NO match found after deep review. Output ONLY one value."
      },
      {
        "id": 14,
        "text": "What COI rule applies to this management plan?",
        "prompt": "Perform a DEEP RULE-BY-RULE ANALYSIS. 1. If Question 13 is 'NA', return 'NA'. 2. Retrieve the Policy Name from Question 13 and look it up in REFERENCE_POLICIES. 3. Evaluate ALL Rules provided under that Policy. 4. Select the SINGLE Rule that has the MAXIMUM matched conditions. 5. Output ONLY the EXACT value of the 'Name' field from the matched rule object in REFERENCE_POLICIES. Do NOT return multiple rules. Do NOT return lists. If the Policy is a single object (not a list), return its Name from rule section."
      },
      {
        "id": 15,
        "text": "Is the researcher petitioning for an exemption from a COI rule?",
        "prompt": "Perform a DEEP SEMANTIC LEGAL SEARCH for any mention of petition, exemption, exception, waiver, rebuttable presumption, or appeal. Output Yes if mentioned, No if explicitly denied, or NA if not referenced."
      }
    ],

    "REFERENCE_POLICIES": {
      "HMS_COI_Policy": {
        "Rules": [
          {
            "ID": "A1",
            "Name": "Clinical Research Rule (formerly the “1(a) Rule”)",
            "Rule": [
              "The individual participates in clinical research involving the company’s technology.",
              "The individual receives equity compensation (e.g., stock, stock options) from the company.",
              "The company providing equity is privately held.",
              "The individual receives cash compensation from the company exceeding $25,000 per year."
            ]
          },
          {
            "ID": "A2",
            "Name": "Research Support Rule (formerly the “1(b) Rule”)",
            "Rule": [
              "The individual receives equity compensation (e.g., stock, stock options) from the company.",
              "The company providing equity is privately held.",
              "The company sponsors or intends to sponsor research conducted in the individual’s laboratory."
            ]
          },
          {
            "ID": "A3",
            "Name": "Executive Position Rule (formerly the “1(c) Rule”)",
            "Rule": [
              "The individual holds or seeks to hold an executive role within the company (e.g., CEO, COO, CSO, CMO, or another role with material responsibility for company operations or management). Most importantly, scientific advisory board positions do not count as executive management positions.",
              "The company is for-profit.",
              "The individual participates in clinical research involving the company’s technology.",
              "The individual receives sponsored research funding from the company.",
              "The individual holds a full-time or part-time HMS faculty appointment."
            ]
          },
          {
            "ID": "A4",
            "Name": "External Activity Rule (formerly the “1(d) Rule”)",
            "Rule": [
              "The individual holds or seeks to hold a fiduciary role with the company (e.g., Board of Directors position).",
              "The company is for-profit.",
              "The individual participates in clinical research involving the company’s technology.",
              "The individual receives sponsored research funding from the company."
            ]
          }
        ]
      },

      "PHS_COI_Policy": {
        "Rules": [
          {
            "Name": "PHS FCOI Rule",
            "Intent": "Ensure management of Financial Conflict of Interest (FCOI) in PHS-funded research",
            "Condition": "Equity in privately held company related to PHS-funded research project",
            "Action": "Develop a conflict of interest management plan if FCOI exists"
          }
        ]
      },

      "Inventor_Equity_and_Licensing_Conflict_Policy": {
        "Name": "Inventor Equity and Licensing Conflict Policy Rule",
        "Rule": "When an individual has equity in the private company and is the inventor or co-inventor of technology and BCH aims or discussion to obtain a license to develop and commercialize the technology."
      },

      "BCH_COI_Policy": {
        "Name": "BCH COI Policy Rule",
        "Rule": "Boston Children’s has a rebuttable presumption that members of the senior leadership team will not participate in outside for-profit Fiduciary Roles. The presumption can be overcome when there are compelling reasons that the for-profit Fiduciary Role will advance the mission of Boston Children’s Hospital."
      }
    }
  }
}


QUESTIONS = QUESTIONS_DATA['QUESTIONS_DATA']['QUESTIONS']
