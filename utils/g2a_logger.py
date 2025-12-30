from datetime import datetime
from models.logic_models import AnalysisResult
from models.sheet_models import Payload


def _g2a_analysis_log_string(
        payload: Payload,
        analysis_result: AnalysisResult
) -> str:
    log_parts = []

    competitor_price = analysis_result.competitive_price
    if competitor_price is None or competitor_price == float('inf'):
        competitor_name = "Max price (fallback)"
        competitor_price = payload.fetched_max_price
    else:
        competitor_name = analysis_result.competitor_name

    if competitor_name:
        log_parts.append(f"- Targeting: {competitor_name} ({competitor_price:.3f})\n")

    price_min_str = f"{payload.fetched_min_price:.3f}" if payload.fetched_min_price is not None else "None"
    price_max_str = f"{payload.fetched_max_price:.3f}" if payload.fetched_max_price is not None else "None"
    log_parts.append(f"- Range: [{price_min_str} - {price_max_str}]\n")

    sellers_below = analysis_result.sellers_below_min
    if sellers_below:
        sellers_info = "; ".join([
            f"{s.seller_name}={s.price:.3f}"
            for s in sellers_below[:3]
        ])
        log_parts.append(f"- Below Min: {sellers_info}\n")

    if analysis_result.top_sellers_for_log:
        log_parts.append("- Top Sellers: ")

        # Sắp xếp dựa trên attribute .price
        sorted_offers = sorted(analysis_result.top_sellers_for_log, key=lambda o: o.price)

        top_str = "; ".join([
            f"{offer.seller_name}={offer.price:.3f}"
            for offer in sorted_offers[:4]
        ])
        log_parts.append(top_str + "\n")

    return "".join(log_parts)


def get_g2a_log_string(
        mode: str,
        payload: Payload,
        final_price: float,
        analysis_result: AnalysisResult = None
) -> str:
    timestamp = datetime.now().strftime("%d/%m %H:%M")

    prefix = ""
    base_message = ""

    # --- NHÓM UPDATE ---
    if mode == "not_compare":
        prefix = "UPDATE"
        base_message = f"Cập nhật (Ko so sánh): {final_price:.3f}"
    elif mode == "compare":
        prefix = "UPDATE"
        base_message = f"Cập nhật thành công: {final_price:.3f}"

    # --- NHÓM SKIP ---
    elif mode == "below_min":
        prefix = "SKIP"
        min_val = payload.get_min_price_value()
        base_message = f"Giá tính toán ({final_price:.3f}) thấp hơn Min ({min_val:.3f})"
    elif mode == "no_min_price":
        prefix = "SKIP"
        base_message = "Chưa cài đặt Min Price."
    elif mode == "equal":
        prefix = "SKIP"
        base_message = f"Giá hiện tại ({final_price:.3f}) đã khớp mục tiêu"

    # Format hiển thị
    full_log = f"{prefix}\n[{timestamp}] {base_message}\n"

    if analysis_result:
        full_log += _g2a_analysis_log_string(payload, analysis_result)

    return full_log