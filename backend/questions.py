QUESTIONS_DATA = { 

  "global_instructions": { 

    "output_only_value": True, 

    "no_explanations": True, 

    "multiple_values_format": "Ans1,Ans2", 

    "missing_value": "NA", 

    "yes_no_values": ["Yes", "No"], 

    "rules_reference_instruction": "For questions 13, 14, 15, refer to the provided HMS_COI_Policy and PHS_COI_Policy rules to find the answer. Do not hallucinate." 

  }, 

  "QUESTIONS": [ 

    { 

      "id": 1, 

      "text": "Is the researcher a cofounder in a company outside of BCH?", 

      "prompt": "Extract the data from the input and determine whether the researcher is a cofounder in a company outside of BCH. Output Yes or No. If not mentioned, return 'No'." 

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

      "prompt": "Extract the data from the input and identify the annual cash compensation. Apply de minimis threshold logic from HMS_COI_Policy: Income ≤ $25,000 annually. Return the value with a '$' symbol (e.g. '$10,000'). If explicitly none, return $0. If not mentioned, return NA. Refer to HMS_COI_Policy rules for guidance." 

    }, 

    { 

      "id": 6, 

      "text": "How much time/effort does the researcher spend working for the company?", 

      "prompt": "Extract the data from the input and identify time or effort spent working for the company. You MUST convert all time values into a percentage of full-time effort (FTE). ASSUMPTIONS: Full-time = 40 hours/week (160 hours/month). CALCULATION: (Hours / 40) * 100. RULES: If calculated % > 20, return '>20 %'. If calculated % <= 20, return '<20 %'. If already %, apply the same relative logic. Return ONLY the string '>20 %' or '<20 %'. If not mentioned, return NA." 

    }, 

    { 

      "id": 7, 

      "text": "Has the company licensed or is it planning to license intellectual property from BCH?", 

      "prompt": "Extract the data from the input and determine whether the company has licensed or plans to license intellectual property from BCH. Output Yes or No. If not mentioned, return NA." 

    }, 

    { 

      "id": 8, 

      "text": "Will BCH receive equity or financial consideration from the company? If so, how much?", 

      "prompt": "Extract the data from the input and determine if BCH receives any equity ownership percentage, cash payments, milestones, or royalties. Focus on revenue, savings, or equity logic; do NOT include costs. Return the specific Equity % and/or Cash Amount/Type (e.g., '5% Equity', '$100k Milestone', 'Royalties on Net Sales'). If multiple, return values comma-separated. If explicitly 'None' or not mentioned, return NA." 

    }, 

    { 

      "id": 9, 

      "text": "Does the researcher have any grants or research projects that relate to the company?", 

      "prompt": "Extract the data from the input and determine if the researcher has any grants or research projects related to the company. Output Yes or No. If not mentioned, return NA." 

    }, 

    { 

      "id": 10, 

      "text": "Is the related research clinical or basic?", 

      "prompt": "Extract the data from the input and determine whether the related research is Clinical or Basic. If not mentioned, return NA." 

    }, 

    { 

      "id": 11, 

      "text": "Is the researcher participating in clinical research related to the company’s technology?", 

      "prompt": "Extract the data from the input and determine whether the researcher participates in clinical research related to the company’s technology. Output Yes or No. If not mentioned, return NA." 

    }, 

    { 

      "id": 12, 

      "text": "Is the company seeking to sponsor research at BCH?", 

      "prompt": "Extract the data from the input and determine whether the company seeks to sponsor research at BCH. Output Yes or No. If not mentioned, return NA." 

    }, 

    { 

      "id": 13, 

      "text": "What COI policy applies to this management plan?", 

      "prompt": "Extract the data from the input. Output ONLY one value: HMS_COI_Policy or PHS_COI_Policy. Refer to the 'HMS_COI_Policy' and 'PHS_COI_Policy' sections in the provided REFERENCE POLICIES to compare conditions. If unclear, return NA." 

    }, 

    { 

      "id": 14, 

      "text": "What COI rule applies to this management plan?", 

      "prompt": "Extract the data from the input. Review the 'Rules' array within 'HMS_COI_Policy' and 'PHS_COI_Policy' in the REFERENCE POLICIES. Select the Exact Rule Name from REFERENCE POLICIES that BEST FITS the scenario. If multiple apply, return Name1,Name2. If none, return NA." 

    }, 

    { 

      "id": 15, 

      "text": "Is the researcher petitioning for an exemption from a COI rule?", 

      "prompt": "Extract the data from the input and perform a DEEP semantic search for any mention of a petition, exemption, exception, waiver, or appeal. Refer to the 'Exceptions' field within the 'HMS_COI_Policy' rules for context. If absolutely no mention found, return NA." 

    } 

  ], 

  "REFERENCE_POLICIES": { 

    "HMS_COI_Policy": { 

      "Rules": [ 

        { 

          "ID": "A1", 

          "Name": "Clinical Research Rule (formerly the “1(a) Rule”)", 

          "Intent": "Prevent Faculty with significant Financial Interests from introducing bias in Clinical Research.", 

          "Conditions": [ 

            "Faculty participates in Clinical Research", 

            "Financial Interest exceeds de minimis thresholds" 

          ], 

          "Actions": [ 

            

            "Compliance continues for entire duration of Research", 

            "Participation rules continue even after termination", 

            "Petition Standing Committee for exceptions with compelling justification" 

          ], 

          "DeMinimisThresholds": { 

            "Income": "$25,000 or less annually", 

            "EquityPublic": "$50,000 or less in publicly held Business (not given in connection with Research)", 

            "EquityPrivate": "Any equity in a privately held Company is presumed prohibited" 

          }, 

          "Exceptions": [ 

            "Dual-Career Family Exception", 

            "Institutional License/Royalty Sharing Agreement Exception" 

          ], 

          "ReviewFactors": [ 

            "Nature of proposed Research", 

            "Anticipated role", 

            "Nature of Financial Interest", 

            "Relationship between Financial Interest and Research", 

            "Impact on trainees", 

            "Role in intellectual property", 

            "Best interests of study participants", 

            "Likely effectiveness of management strategies" 

          ], 

          "Duration": [ 

            "Six (6) months after last participant completes Research", 

            "First publication or decision not to publish Research data" 

          ] 

        }, 

        { 

          "ID": "A2", 

          "Name": "Research Support Rule (formerly the “1(b) Rule”)", 

          "Intent": "Prevent bias in Sponsored Research due to Faculty Equity Financial Interests.", 

          "Conditions": [ 

            "Faculty has Equity Financial Interest above de minimis thresholds", 

            "Faculty seeks Sponsored Research support from Business" 

          ], 

          "Actions": [ 

         

            "Faculty may petition for exception if benefits outweigh risks" 

          ], 

          "DeMinimisThresholds": { 

            "EquityPublic": "1% or less of publicly-traded Business permitted under conditions", 

            "EquityPrivate": "Any equity in privately held Business requires exception" 

          }, 

          "SponsoredResearchIncludes": [ 

            "Research, training, instructional projects involving funds, personnel, proprietary materials, or Technology", 

            "Gifts solely for Research support", 

            "Proprietary material giving Business intellectual/tangible property rights" 

          ], 

          "Exceptions": [ 

            "SBIR/STTR Exception (basic Research only, requires institutional management plan)" 

          ], 

          "ReviewFactors": [ 

            "Nature of Research", 

            "Role of Faculty", 

            "Financial Interest relationship", 

            "Impact on Research and trainees", 

            "Effectiveness of management strategies" 

          ], 

          "Duration": [ 

            "Six (6) months after data collection ends", 

            "First publication or decision not to publish" 

          ] 

        }, 

        { 

          "ID": "A3", 

          "Name": "External Activity Rule (formerly the “1(d) Rule”)", 

          "Intent": "Prevent Faculty fiduciary roles from influencing Clinical Research or Sponsored Research.", 

          "Conditions": [ 

            "Faculty serves in fiduciary role to for-profit Business" 

          ], 

          "Actions": [ 

            "Faculty may not participate in Clinical Research on the Business’s Technology", 

            "Faculty may not receive Sponsored Research support from the Business" 

          ], 

          "Exceptions": [ 

            "Scientific Advisory Board service is not a fiduciary role", 

            "SBIR/STTR Exception for basic Research only" 

          ] 

        }, 

        { 

          "ID": "B", 

          "Name": "Executive Position Rule (formerly the “1(c) Rule”)", 

          "Intent": "Prevent bias from Faculty holding Executive Positions in biomedical Businesses.", 

          "Conditions": [ 

            "Full-time Faculty hold Executive Position", 

            "Part-time Faculty hold approved Executive Position" 

          ], 

          "Actions": [ 

            "Full-time Faculty may not participate in Clinical Research or receive Sponsored Research from the Business", 

            "Part-time Faculty may hold Executive Position but may not participate in Clinical Research or receive Sponsored Research from the Business" 

          ] 

        }, 

        { 

          "ID": "C", 

          "Name": "Prohibition of Industry Control over Academic Content", 

          "Intent": "Ensure Faculty retain independence in educational content.", 

          "Conditions": [ 

            "Events or speakers bureaus sponsored by for-profit Business", 

            "Business exerts control over content, tone, or views" 

          ], 

          

        }, 

        { 

          "ID": "D", 

          "Name": "Ghostwriting Rule", 

          "Intent": "Prevent attribution of authorship without intellectual contribution.", 

          "Conditions": [ 

            "Faculty identified as author but did not contribute meaningfully" 

          ], 

          "Actions": [ 

            "Faculty must make significant intellectual/practical contribution", 

            "Ghostwriting and honorary authorship prohibited", 

            "Violations subject to review and possible sanction" 

          ] 

        }, 

        { 

          "ID": "E", 

          "Name": "Prohibition of Industry Sponsored Gifts/Meals/Travel", 

          "Intent": "Prevent undue influence from industry gifts or travel on Faculty decisions.", 

          "Conditions": [ 

            "Soliciting or accepting gifts, meals, registration fees, or travel reimbursement from pharmaceutical, medical device, or biotech companies" 

          ], 

          

          "Exceptions": [ 

            "Contractually Required Meetings Exception: Modest meals may be accepted if attendance is contractually required" 

          ] 

        } 

      ] 

    }, 

    "PHS_COI_Policy": { 

      "Rules": [ 

        { 

          "Name": "PHS FCOIRule", 

          "Intent": "Ensure management of Financial Conflict of Interest (FCOI) in PHS-funded research", 

          "Condition": "Equity in privately held company related to PHS-funded research project", 

          "Action": "Develop a conflict of interest management plan if FCOI exists" 

        } 

      ] 

    } 

  } 

} 

 

QUESTIONS = QUESTIONS_DATA["QUESTIONS"] 
