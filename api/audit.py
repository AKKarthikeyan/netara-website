import json
import re

def calculate_irr(premiums, maturity_value, years):
    total = sum(premiums)
    if total == 0 or years == 0: return 0
    return ((maturity_value / total) ** (1/years) - 1) * 100

def fv_leakage(annual_leakage, years, rate=0.12):
    fv = 0
    for i in range(years):
        fv += annual_leakage * ((1 + rate) ** (years - 1 - i))
    return fv

def analyze(funds, insurance=None, gold=None, equity=None):
    regular = [f for f in funds if f.get('plan') == 'Regular']
    leakage_report = []
    for f in regular:
        val = f.get('value', 0)
        leak = val * 0.01
        leakage_report.append({
            'scheme_name': f.get('name', ''),
            'current_value': val,
            'annual_leakage': leak,
            'leakage_5yr_compounded': fv_leakage(leak, 5),
            'leakage_10yr_compounded': fv_leakage(leak, 10)
        })

    insurance_audit = []
    if insurance:
        for p in insurance:
            irr = calculate_irr(p.get('premiums', []), p.get('maturity_value', 0), p.get('years', 0))
            insurance_audit.append({
                'policy_name': p.get('name', ''),
                'irr': round(irr, 2),
                'opportunity_cost': p.get('maturity_value', 0) * (0.12 - irr/100)
            })

    gold_audit = []
    if gold:
        for g in gold:
            cost = g.get('current_value', 0) * 0.03
            gold_audit.append({
                'type': g.get('type', 'Gold'),
                'current_value': g.get('current_value', 0),
                'annual_leakage': cost,
                'leakage_10yr_compounded': fv_leakage(cost, 10)
            })

    equity_audit = []
    if equity:
        for e in equity:
            leak = e.get('brokerage', 0) + e.get('stt', 0) + e.get('idle_cash', 0) * 0.12
            equity_audit.append({
                'type': e.get('type', 'Equity'),
                'annual_leakage': leak,
                'leakage_10yr_compounded': fv_leakage(leak, 10)
            })

    mf_leak   = sum(x['annual_leakage'] for x in leakage_report)
    gold_leak = sum(x['annual_leakage'] for x in gold_audit)
    eq_leak   = sum(x['annual_leakage'] for x in equity_audit)
    total_aum = sum(f.get('value', 0) for f in funds)

    return {
        'regular_vs_direct_leakage': leakage_report,
        'total_annual_leakage': mf_leak + gold_leak + eq_leak,
        'leakage_breakdown': {
            'mutual_funds': mf_leak,
            'gold': gold_leak,
            'equity': eq_leak
        },
        'insurance_audit': insurance_audit,
        'gold_audit': gold_audit,
        'equity_audit': equity_audit,
        'portfolio_summary': {
            'total_funds': len(funds),
            'regular_funds': len(regular),
            'direct_funds': len(funds) - len(regular),
            'total_aum': total_aum,
            'regular_aum': sum(f.get('value', 0) for f in regular),
            'direct_aum': sum(f.get('value', 0) for f in funds if f.get('plan') == 'Direct')
        }
    }

def parse_cams_text(text):
    """Parse raw text from CAMS PDF into fund list."""
    funds = []
    blocks = re.split(r'(?=Folio\s*No\s*:)', text, flags=re.IGNORECASE)
    for block in blocks:
        if not block.strip(): continue
        scheme_match = re.search(
            r'\n\s*([A-Z][^\n]{10,120}?(?:Direct|Regular)[^\n]{0,60}?(?:Growth|Dividend|IDCW|Bonus))\s*\n',
            block, re.IGNORECASE
        )
        if not scheme_match:
            scheme_match = re.search(
                r'\n\s*([A-Z][A-Za-z0-9\s\-&]+(?:Fund|Scheme)[^\n]*)\n',
                block, re.IGNORECASE
            )
        if not scheme_match: continue
        full_name = scheme_match.group(1).strip()
        if re.search(r'\bDirect\b', full_name, re.IGNORECASE): plan = 'Direct'
        elif re.search(r'\bRegular\b', full_name, re.IGNORECASE): plan = 'Regular'
        else: plan = 'Direct' if re.search(r'Advisor\s*:\s*DIRECT', block, re.IGNORECASE) else 'Regular'
        clean = re.sub(r'\s*[-\u2013]\s*(Direct|Regular)\s*(Plan)?\s*[-\u2013]?\s*(Growth|Dividend|IDCW|Bonus)?.*$', '', full_name, flags=re.IGNORECASE).strip()
        val_match = re.search(r'(?:Market\s+)?Value\s*:?\s*(?:Rs\.?|INR|\u20b9)\s*([\d,]+\.?\d*)', block, re.IGNORECASE)
        if not val_match: continue
        value = float(val_match.group(1).replace(',', ''))
        if value <= 0: continue
        funds.append({'name': clean, 'plan': plan, 'value': value})
    return funds

def handler(request):
    # Handle CORS preflight
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Type': 'application/json'
    }

    if request.method == 'OPTIONS':
        return Response('', 204, headers)

    try:
        body = request.json()
        mode = body.get('mode', 'funds')

        if mode == 'parse_text':
            # Parse raw PDF text → fund list
            raw_text = body.get('text', '')
            funds = parse_cams_text(raw_text)
            return Response(json.dumps({'funds': funds, 'count': len(funds)}), 200, headers)

        elif mode == 'analyze':
            # Run full audit on fund list + optional data
            funds    = body.get('funds', [])
            result   = analyze(
                funds,
                insurance = body.get('insurance'),
                gold      = body.get('gold'),
                equity    = body.get('equity')
            )
            return Response(json.dumps({'net_yield_calculator_input': result}), 200, headers)

        else:
            return Response(json.dumps({'error': 'Invalid mode'}), 400, headers)

    except Exception as e:
        return Response(json.dumps({'error': str(e)}), 500, headers)
