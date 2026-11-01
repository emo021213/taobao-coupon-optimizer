import pandas as pd


def calc_discount(cart_items, coupons):
    flow_list = []
    result = {"流水": flow_list, "实付": 0.0}
    total_original = sum(it["price"] for it in cart_items)
    current_total = total_original

    # 1. 扣减单品券面额
    item_coupons_total = 0
    for it in cart_items:
        coupon_amt = it.get("单品券面额", it.get("单品券", it.get("商品券", 0)))
        item_coupons_total += coupon_amt
    if item_coupons_total > 0:
        current_total -= item_coupons_total
        flow_list.append(f"1. 扣减单品券：-{item_coupons_total:.2f} 元")

    # 2. 88VIP 95折
    if coupons.get("是88VIP", False):
        vip_discount = current_total * 0.05
        current_total -= vip_discount
        flow_list.append(f"2. 88VIP 95折：-{vip_discount:.2f} 元")

    # 3. 主播券
    if "主播券" in coupons and coupons["主播券"]["折扣率"] > 0:
        c = coupons["主播券"]
        host_items = [it for it in cart_items if it.get("主播券")]
        host_total = sum(it["price"] for it in host_items)

        if host_total > 0:
            theoretical_discount = host_total * (1 - c["折扣率"])
            zb_discount = min(theoretical_discount, c["封顶"], current_total)
            current_total -= zb_discount

            names_list = []
            for it in host_items:
                name = str(it.get("title", ""))
                if name == "nan" or name == "None" or not name.strip():
                    name = "凑单品"
                names_list.append(name)
            host_names = "+".join(names_list)

            status = "完全抵扣" if theoretical_discount <= c["封顶"] else f"触发封顶(上限{c['封顶']}元)"
            flow_list.append(f"3. 主播券：减 {zb_discount:.2f} 元 ({status}，商品: {host_names})")
        else:
            flow_list.append("3. 主播券：无可用商品，未抵扣")

    # 4. 品类券
    for jx in coupons.get("惊喜券列表", []):
        tag = jx["标签"]
        threshold = jx["门槛"]
        amount = jx["面额"]

        tag_items = [it for it in cart_items if it.get("券标签") in [tag, "通用"]]
        tag_pay = 0.0
        if tag_items:
            for it in tag_items:
                item_price = it["price"]
                item_coupon = it.get("单品券面额", it.get("单品券", it.get("商品券", 0)))
                item_pay = item_price - item_coupon
                if coupons.get("是88VIP", False):
                    item_pay *= 0.95
                if "主播券" in coupons and coupons["主播券"]["折扣率"] > 0 and it.get("主播券"):
                    c = coupons["主播券"]
                    item_pay -= min(item_pay * (1 - c["折扣率"]), c["封顶"])
                tag_pay += item_pay

            names_list = []
            for it in tag_items:
                name = str(it.get("title", ""))
                if name == "nan" or name == "None" or not name.strip():
                    name = "凑单品"
                names_list.append(name)
            item_names = "+".join(names_list)

            if tag_pay >= threshold:
                current_total -= amount
                flow_list.append(
                    f"4. {jx['名称']}：达标，减 {amount:.2f} 元 (凑单商品: {item_names}, 券前实付:{tag_pay:.2f})")
            else:
                flow_list.append(
                    f"4. {jx['名称']}：未满 {threshold}，未抵扣 (凑单商品: {item_names}, 券前实付:{tag_pay:.2f})")

    # 5. 消费券
    if "消费券" in coupons:
        c = coupons["消费券"]
        xf_items = [it for it in cart_items if it.get("消费券") == 1]
        names_list = []
        for it in xf_items:
            name = str(it.get("title", ""))
            if name == "nan" or name == "None" or not name.strip():
                name = "凑单品"
            names_list.append(name)
        xf_names = "+".join(names_list) if names_list else "全场通用"

        if current_total >= c["门槛"]:
            current_total -= c["面额"]
            flow_list.append(
                f"5. 消费券：达标，减 {c['面额']:.2f} 元 (凑单商品: {xf_names}, 券前实付:{current_total + c['面额']:.2f})")
        else:
            flow_list.append(f"5. 消费券：未满 {c['门槛']}，未抵扣 (凑单商品: {xf_names}, 券前实付:{current_total:.2f})")

    # 6. 红包抵扣
    if "红包" in coupons and coupons["红包"].get("面额", 0) > 0:
        hb_amount = coupons["红包"]["面额"]
        hb_items = [it for it in cart_items if it.get("红包") in [1, True]]

        if hb_items:
            actual_hb = min(hb_amount, current_total)
            current_total -= actual_hb

            names_list = []
            for it in hb_items:
                name = str(it.get("title", ""))
                if name == "nan" or name == "None" or not name.strip():
                    name = "凑单品"
                names_list.append(name)
            hb_names = "+".join(names_list)

            flow_list.append(f"6. 红包抵扣：-{actual_hb:.2f} 元 (商品: {hb_names})")
        else:
            flow_list.append(f"6. 红包：未找到可用红包商品，未抵扣")

    result["实付"] = max(current_total, 0.0)
    return result


def find_combination(cart_items, coupons, candidate_df, max_item_count_limit=50, max_overflow=100.0):
    pool = candidate_df.copy()
    chosen_items = []
    used_tags = set()

    def get_res(current_cart):
        temp_cart = []
        for it in current_cart:
            copy_item = it.copy()
            copy_item["单品券面额"] = it.get("单品券面额", it.get("单品券", it.get("商品券", 0)))
            copy_item["title"] = it.get("title", "凑单品")
            temp_cart.append(copy_item)
        return calc_discount(temp_cart, coupons)

    def get_tag_pay(current_cart, tag):
        tag_pay = 0.0
        for it in current_cart:
            if it.get("券标签") not in [tag, "通用"]:
                continue
            item_coupon = it.get("单品券面额", it.get("单品券", it.get("商品券", 0)))
            item_pay = it["price"] - item_coupon
            if coupons.get("是88VIP", False):
                item_pay *= 0.95
            if "主播券" in coupons and coupons["主播券"]["折扣率"] > 0 and it.get("主播券"):
                c = coupons["主播券"]
                item_pay -= min(item_pay * (1 - c["折扣率"]), c["封顶"])
            tag_pay += item_pay
        return tag_pay

    # ---------------- 阶段一：死磕品类券 ----------------
    for jx in coupons.get("惊喜券列表", []):
        tag = jx["标签"]
        used_tags.add(tag)
        tag_lower = jx["门槛"]
        tag_upper = jx["门槛"] + max_overflow

        best_temp_chosen = []
        best_pay = 0.0
        found_success = False

        for skip_count in [0, 1, 3, 5, 10]:
            temp_chosen = []
            base_pool = pool[pool["券标签"].isin([tag, "通用"])].sort_values(by="price", ascending=False)
            if skip_count > 0:
                base_pool = base_pool.iloc[skip_count:]

            while len(temp_chosen) < max_item_count_limit:
                current_cart = cart_items + temp_chosen
                current_tag_pay = get_tag_pay(current_cart, tag)

                if current_tag_pay >= tag_lower:
                    found_success = True
                    break

                picked = None
                for _, row in base_pool.iterrows():
                    if str(row.name) in [str(c["_row_id"]) for c in temp_chosen]:
                        continue
                    test_cart = current_cart + [row.to_dict()]
                    test_tag_pay = get_tag_pay(test_cart, tag)
                    if test_tag_pay > tag_upper:
                        continue
                    picked = row
                    break

                if picked is None:
                    break

                new_item = picked.to_dict()
                new_item["_row_id"] = picked.name
                real_name = str(new_item.get("title", ""))
                if real_name == "nan" or not real_name.strip():
                    real_name = "凑单品"
                new_item["title"] = real_name
                temp_chosen.append(new_item)

            final_pay = get_tag_pay(cart_items + temp_chosen, tag)
            if found_success:
                chosen_items.extend(temp_chosen)
                break
            else:
                if final_pay > best_pay:
                    best_pay = final_pay
                    best_temp_chosen = temp_chosen

        if not found_success and best_temp_chosen:
            chosen_items.extend(best_temp_chosen)

    # ---------------- 阶段二：死磕消费券 ----------------
    if "消费券" in coupons:
        xf_threshold = coupons["消费券"]["门槛"]
        xf_amount = coupons["消费券"]["面额"]
        xf_max_pay = xf_threshold - xf_amount + max_overflow

        while len(chosen_items) < max_item_count_limit:
            current_cart = cart_items + chosen_items
            res = get_res(current_cart)
            if any("消费券：达标" in line for line in res["流水"]):
                break

            chosen_ids = [str(c.get("_row_id", "")) for c in chosen_items]
            avail_pool = pool[
                (~pool.index.astype(str).isin(chosen_ids)) &
                (pool["消费券"] == 1) &
                (~pool["券标签"].isin(used_tags))
                ].sort_values(by="price", ascending=False)

            picked = None
            for _, row in avail_pool.iterrows():
                test_cart = current_cart + [row.to_dict()]
                test_res = get_res(test_cart)
                if test_res["实付"] > xf_max_pay:
                    continue
                picked = row
                break

            if picked is None:
                break

            new_item = picked.to_dict()
            new_item["_row_id"] = picked.name
            real_name = str(new_item.get("title", ""))
            if real_name == "nan" or not real_name.strip():
                real_name = "凑单品"
            new_item["title"] = real_name
            chosen_items.append(new_item)

    # ---------------- 分摊算法 ----------------
    if not chosen_items:
        return [], 0, "找不到合适的商品。"

    all_cart = cart_items + chosen_items

    coupons_no_hb = coupons.copy()
    if "红包" in coupons_no_hb:
        del coupons_no_hb["红包"]

    temp_res = calc_discount(all_cart, coupons_no_hb)

    for c in all_cart:
        c_cp = c.get("单品券面额", 0)
        base = c["price"] - c_cp
        if coupons.get("是88VIP", False): base *= 0.95
        if coupons.get("主播券", {}).get("折扣率", 0) > 0 and c.get("主播券"):
            base -= min(base * (1 - coupons["主播券"]["折扣率"]), coupons["主播券"]["封顶"])
        c["_current_pay"] = base

    for jx in coupons.get("惊喜券列表", []):
        tag = jx["标签"]
        amount = jx["面额"]
        if any(f"{jx['名称']}：达标" in line for line in temp_res["流水"]):
            tag_items = [c for c in all_cart if c.get("券标签") in [tag, "通用"]]
            tag_total = sum(c["_current_pay"] for c in tag_items)
            if tag_total > 0:
                for c in tag_items:
                    share = c["_current_pay"] / tag_total
                    c["_current_pay"] -= amount * share

    if "消费券" in coupons:
        xf_amount = coupons["消费券"]["面额"]
        if any("消费券：达标" in line for line in temp_res["流水"]):
            total_current = sum(c["_current_pay"] for c in all_cart)
            if total_current > 0:
                for c in all_cart:
                    share = c["_current_pay"] / total_current
                    c["_current_pay"] -= xf_amount * share

    for c in all_cart:
        c["_current_pay"] = max(c["_current_pay"], 0.0)

    if "红包" in coupons and coupons["红包"].get("面额", 0) > 0:
        hb_amount = coupons["红包"]["面额"]
        hb_items = [c for c in all_cart if c.get("红包") in [1, True]]
        hb_total = sum(c["_current_pay"] for c in hb_items)
        if hb_total > 0:
            actual_hb = min(hb_amount, hb_total)
            for c in hb_items:
                share = c["_current_pay"] / hb_total
                c["_current_pay"] -= actual_hb * share
                c["_current_pay"] = max(c["_current_pay"], 0.0)

    selected_dict = {}
    total_extra = 0
    for c in chosen_items:
        key = c["title"]
        if key not in selected_dict:
            selected_dict[key] = {"title": key, "price": c["price"], "final_price": c["_current_pay"],
                                  "券标签": c.get("券标签", "无"), "消费券": c.get("消费券", 0), "count": 1}
        else:
            selected_dict[key]["count"] += 1
            selected_dict[key]["final_price"] += c["_current_pay"]
        total_extra += c["price"]

    selected_list = []
    for k, v in selected_dict.items():
        title_display = f"{v['title']} x {v['count']}件" if v['count'] > 1 else v['title']
        selected_list.append(pd.Series({
            "title": title_display,
            "price": v['price'] * v['count'],
            "final_price": v['final_price'],
            "券标签": v["券标签"],
            "消费券": v["消费券"]
        }))

    final_res = calc_discount(all_cart, coupons)

    return selected_list, total_extra, f"实付严格卡在红线内！最终实付：¥{final_res['实付']:.2f}", all_cart