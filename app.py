
import streamlit as st
import pandas as pd
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from solver import calc_discount, find_combination

st.set_page_config(page_title="多券凑单优化器", layout="wide")
st.title("🛒 淘宝多券叠加凑单优化系统")


@st.cache_data
def load_data():
    file_path = "products_full.csv"
    if not os.path.exists(file_path):
        st.error(f"未找到 {file_path}，请先确保数据文件存在！")
        st.stop()
    try:
        return pd.read_csv(file_path, encoding="utf-8-sig")
    except:
        return pd.read_csv(file_path, encoding="gbk")


df = load_data()
all_tags = [str(t) for t in df["券标签"].unique() if str(t) not in ["nan", "通用"]]

with st.sidebar:
    st.header("1. 模拟您的购物车")
    if "cart_df" not in st.session_state:
        # 初始化时增加 title 列
        st.session_state.cart_df = pd.DataFrame([
            {"title": "我的衣服", "价格": 250.0, "单品券面额": 50.0, "主播券": False, "券标签": "美妆", "消费券": True,
             "红包": False},
            {"title": "我的耳机", "价格": 80.0, "单品券面额": 10.0, "主播券": True, "券标签": "无", "消费券": True,
             "红包": True},
        ])

    if "单品券面额" not in st.session_state.cart_df.columns:
        st.session_state.cart_df["单品券面额"] = 0.0
    if "title" not in st.session_state.cart_df.columns:
        st.session_state.cart_df["title"] = "我的商品"

    cart_edited = st.data_editor(
        st.session_state.cart_df,
        num_rows="dynamic",
        column_config={
            "title": st.column_config.TextColumn("商品名称", required=True),  # 新增名称列
            "价格": st.column_config.NumberColumn("价格", min_value=0.0, format="%.2f"),
            "单品券面额": st.column_config.NumberColumn("单品券面额", min_value=0.0, format="%.2f"),
            "主播券": st.column_config.CheckboxColumn("可用主播券"),
            "券标签": st.column_config.SelectboxColumn("适用品类", options=all_tags + ["无"]),
            "消费券": st.column_config.CheckboxColumn("可用消费券"),
            "红包": st.column_config.CheckboxColumn("可用红包")
        }
    )

    st.header("2. 填写优惠券规则")
    is_vip = st.checkbox("参与 88VIP 95折", value=True)

    with st.expander("主播折扣券", expanded=False):
        zb_rate = st.number_input("主播券折扣率", value=0.9, step=0.05)
        zb_cap = st.number_input("主播券封顶金额", value=20.0)

    st.write("**多品类加补券（可多选）**")
    selected_tags = st.multiselect("选择要凑的加补券品类", sorted(all_tags),
                                   default=[sorted(all_tags)[0]] if all_tags else [])

    jx_coupons_list = []
    for tag in selected_tags:
        th = st.number_input(f"{tag}券门槛", value=300.0, key=f"th_{tag}")
        amt = st.number_input(f"{tag}券面额", value=30.0, key=f"amt_{tag}")
        jx_coupons_list.append({"名称": f"{tag}加补券", "标签": tag, "门槛": th, "面额": amt})

    st.write("**平台消费券**")
    xf_th = st.number_input("消费券门槛", value=300.0)
    xf_amt = st.number_input("消费券面额", value=40.0)

    hb_amt = st.number_input("红包面额", value=10.0)

    st.header("3. 凑单限制")
    max_overflow = st.number_input("最多允许超出差额多少元？", value=30.0, step=10.0)
    max_item_count = st.slider("最多允许凑单几件商品？", min_value=1, max_value=30, value=10)

    calc_btn = st.button("🚀 计算最优凑单方案", type="primary")

if calc_btn:
    cart = []
    for idx, row in cart_edited.iterrows():
        if row["价格"] > 0:
            hb_flag = 1 if row["红包"] else 0
            # 获取自定义名称，如果为空则兜底
            item_title = str(row.get("title", "")).strip()
            if not item_title or item_title == "None" or item_title == "nan":
                item_title = f"已有商品{idx + 1}"

            cart.append({
                "title": item_title,
                "price": row["价格"],
                "单品券面额": row["单品券面额"] if "单品券面额" in row and pd.notna(row["单品券面额"]) else 0.0,
                "主播券": 1 if row["主播券"] else 0,
                "券标签": row["券标签"] if pd.notna(row["券标签"]) else "无",
                "消费券": 1 if row["消费券"] else 0,
                "红包": hb_flag
            })

    coupons = {
        "是88VIP": is_vip,
        "主播券": {"折扣率": zb_rate, "封顶": zb_cap},
        "惊喜券列表": jx_coupons_list,
        "消费券": {"门槛": xf_th, "面额": xf_amt},
        "红包": {"面额": hb_amt}
    }

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎯 推荐凑单方案")
        res_tuple = find_combination(cart, coupons, df, max_item_count_limit=max_item_count, max_overflow=max_overflow)

        if len(res_tuple) == 4:
            sel, extra, msg, all_cart = res_tuple
        else:
            sel, extra, msg = res_tuple
            all_cart = []

        if not sel:
            st.warning(msg)
        else:
            st.success(f"{msg}，需额外支出 **¥{extra:.1f}**")
            for r in sel:
                st.info(
                    f"推荐商品：{r['title']}  \n价格：¥{r['price']} (适用品类:{r['券标签']})  \n**折后实付：¥{r['final_price']:.2f}**")

    with col2:
        st.subheader("🧾 结算流水防击穿校验")

        final_cart = []
        for idx, row in cart_edited.iterrows():
            if row["价格"] > 0:
                hb_flag = 1 if row["红包"] else 0
                item_title = str(row.get("title", "")).strip()
                if not item_title or item_title == "None" or item_title == "nan":
                    item_title = f"已有商品{idx + 1}"

                final_cart.append({
                    "title": item_title,
                    "price": row["价格"],
                    "单品券面额": row["单品券面额"] if "单品券面额" in row and pd.notna(row["单品券面额"]) else 0.0,
                    "主播券": 1 if row["主播券"] else 0,
                    "券标签": row["券标签"] if pd.notna(row["券标签"]) else "无",
                    "消费券": 1 if row["消费券"] else 0,
                    "红包": hb_flag
                })
        if sel:
            for r in sel:
                count = r.get("count", 1)
                for _ in range(count):
                    matched_row = df[df["title"] == r["title"]]
                    single_coupon = matched_row.iloc[0].get("单品券面额", 0) if not matched_row.empty else 0
                    final_cart.append({
                        "title": str(r.get("title", "凑单品")),
                        "price": r["price"] / count,
                        "主播券": 0,
                        "券标签": r["券标签"],
                        "消费券": int(r["消费券"]),
                        "单品券面额": single_coupon,
                        "红包": 0
                    })

        result = calc_discount(final_cart, coupons)
        for line in result["流水"]:
            if "未满" in line:
                st.markdown(f"<span style='color:red'>{line}</span>", unsafe_allow_html=True)
            else:
                st.write(line)
        st.metric("预计最终实付总计", f"¥{result['实付']:.2f}")

        st.divider()
        st.write("**🔍 您的已有商品最终精准分摊实付：**")

        if all_cart:
            for c in all_cart:
                # 现在判断是不是已有商品，可以通过判断它在不在最初传进去的 cart 里
                is_initial_item = any(
                    init_c["title"] == c.get("title") and init_c["price"] == c["price"] for init_c in cart)
                if is_initial_item:
                    st.write(f"- {c['title']} (原价 ¥{c['price']}): **实付 ¥{c['_current_pay']:.2f}**")
