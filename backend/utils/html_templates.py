def generate_search_results_html(results, search_method):
    """
    Generates a professional HTML email body for search results.
    """
    
    html_parts = ["""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; }
            .container { max-width: 800px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #ffffff; }
            .header { background-color: #004d40; color: white; padding: 15px; border-radius: 8px 8px 0 0; text-align: center; }
            .header h2 { margin: 0; font-weight: 600; }
            .meta { background-color: #f5f5f5; padding: 10px 15px; margin-bottom: 20px; border-bottom: 1px solid #ddd; font-size: 0.9rem; }
            .card { margin-bottom: 25px; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
            .card-header { background-color: #e0f2f1; padding: 10px 15px; border-bottom: 1px solid #b2dfdb; display: flex; justify-content: space-between; align-items: center; }
            .pdf-title { font-size: 1.1rem; font-weight: 700; color: #00695c; }
            .score-badge { background-color: #00796b; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.9rem; }
            .card-body { padding: 15px; }
            .details-row { margin-bottom: 10px; font-size: 0.9rem; color: #555; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.85rem; }
            th { background-color: #fafafa; border-bottom: 2px solid #ddd; padding: 8px; text-align: left; font-weight: 600; color: #444; }
            td { padding: 8px; border-bottom: 1px solid #eee; vertical-align: top; }
            .match-row { background-color: #f1f8e9; }
            .mismatch-row { background-color: #fffde7; }
            .notfound-row { background-color: #ffebee; }
            .status-exact { color: #2e7d32; font-weight: 600; }
            .status-mismatch { color: #c62828; font-weight: 600; }
            .footer { margin-top: 30px; font-size: 0.8rem; color: #888; text-align: center; border-top: 1px solid #eee; padding-top: 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>COI Analysis Verification Report</h2>
            </div>
    """]


    for res in results:
        # Check if result is a placeholder
        if res.get("pdf_name") == "No Data Found" or res.get("match_score") == "0%":
             continue

        formatted_score = res.get("match_score", "0%")
        weight_details = res.get("weightage_details", "N/A")
        
        card_html = f"""
            <div class="card">
                <div class="card-header">
                    <span class="pdf-title">📄 {res.get('pdf_name')}</span>
                    <span class="score-badge">Match: {formatted_score}</span>
                </div>
                <div class="card-body">
                    <div class="details-row">
                        <strong>Weighted Score Breakdown:</strong> {weight_details}
                    </div>
                    
                    <table>
                        <thead>
                            <tr>
                                <th style="width: 35%;">Question</th>
                                <th style="width: 20%;">User Input</th>
                                <th style="width: 20%;">PDF Data</th>
                                <th style="width: 15%;">Status</th>
                                <th style="width: 10%;">Weight/Score</th>
                            </tr>
                        </thead>
                        <tbody>
        """
        
        # Combined list for display order? Or verified first?
        # Let's show Matched first, then Unmatched for clarity
        
        all_qa = []
        for m in res.get("matched_qa", []):
            m["_is_match"] = True
            all_qa.append(m)
        for u in res.get("unmatched_qa", []):
             u["_is_match"] = False
             all_qa.append(u)
             
        # Optional: Sort by Weight descending to show high priority first
        all_qa.sort(key=lambda x: x.get("weight", 0), reverse=True)

        for item in all_qa:
            q_text = item.get("question", "")
            user_ans = item.get("user_answer_ref", "")
            pdf_ans = item.get("pdf_answer", "NA")
            
            # Determine Row Style and Status
            if item.get("_is_match"):
                row_class = "match-row"
                status_html = f'<span class="status-exact">✔ {item.get("match_type", "Match")}</span>'
            else:
                 status = item.get("status", "Mismatch")
                 if "Not Found" in status:
                     row_class = "notfound-row"
                     status_html = f'<span class="status-mismatch">❌ {status}</span>'
                 else:
                     row_class = "mismatch-row"
                     status_html = f'<span class="status-mismatch">⚠ {status}</span>'
            
            weight = item.get("weight", 0)
            score = item.get("score_earned", 0)
            
            card_html += f"""
                            <tr class="{row_class}">
                                <td>{q_text}</td>
                                <td>{user_ans}</td>
                                <td>{pdf_ans}</td>
                                <td>{status_html}</td>
                                <td><strong>{score}</strong> <span style="font-size:0.8em;color:#777;">/ {weight}</span></td>
                            </tr>
            """
            
        card_html += """
                        </tbody>
                    </table>
                </div>
            </div>
        """
        html_parts.append(card_html)

    html_parts.append("""
            <div class="footer">
                Generated by COI Management Matching Engine AI Agent
            </div>
        </div>
    </body>
    </html>
    """)
    
    
    # Minify the HTML by stripping whitespace and joining one line
    full_html = "".join(html_parts)
    return " ".join(full_html.split())
