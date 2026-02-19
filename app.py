import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# -----------------------------------
# 1. PAGE SETUP & STYLING
# -----------------------------------
st.set_page_config(page_title="Chadorkart Analytics", layout="wide")

# Custom CSS for professional KPI cards and spacing
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 28px; color: #007bff; }
    .main { background-color: #f8f9fa; }
    div.stButton > button:first-child { background-color: #007bff; color: white; }
    </style>
    """, unsafe_allow_html=True)

st.title("📦 Chadorkart Inventory & Sales")
st.caption("Internal Operations Control Center")

# -----------------------------------
# 2. CACHED DATA ENGINE
# -----------------------------------
@st.cache_data
def process_data(inv_file, sales_file):
    inv = pd.read_csv(inv_file)
    sales = pd.read_csv(sales_file)
    
    inv.columns = inv.columns.str.strip()
    sales.columns = sales.columns.str.strip()

    # Find Order ID
    possible_order_cols = ["Order #", "Order Number", "Order ID", "Order Code"]
    order_id_col = next((c for c in possible_order_cols if c in sales.columns), "Order #")

    # Date Processing
    sales["Uniware Created At"] = pd.to_datetime(sales["Uniware Created At"], errors="coerce")
    
    # SKU Cleanup (Logics preserved)
    sales["Seller SKUs"] = sales["Seller SKUs"].astype(str).str.replace("|", ",", regex=False).str.split(",")
    sales = sales.explode("Seller SKUs")
    sales["Seller SKUs"] = sales["Seller SKUs"].astype(str).str.strip()

    def is_corrupted_sku(sku):
        sku = str(sku)
        return sku.startswith("vof-") or sku.count("-") > 1 or len(sku) > 20

    sales["Final SKU"] = sales.apply(
        lambda x: x["Products"] if is_corrupted_sku(x["Seller SKUs"]) else x["Seller SKUs"],
        axis=1
    )
    sales["Final SKU"] = sales["Final SKU"].astype(str).str.strip()
    sales = sales[sales["Final SKU"] != ""]

    # Status Processing
    status_col = "Order Status" if "Order Status" in sales.columns else "Status"
    sales[status_col] = sales[status_col].astype(str).str.upper()

    return inv, sales, order_id_col, status_col

# -----------------------------------
# 3. FILE UPLOAD & EXECUTION
# -----------------------------------
col_u1, col_u2 = st.columns(2)
inv_file = col_u1.file_uploader("Upload Inventory CSV", type=["csv"])
sales_file = col_u2.file_uploader("Upload Sales CSV", type=["csv"])

if inv_file and sales_file:
    inv, sales, order_id_col, status_col = process_data(inv_file, sales_file)

    # Filtered Datasets
    cancelled_orders = sales[sales[status_col].str.contains("CANCEL", na=False)].copy()
    completed_sales = sales[~sales[status_col].str.contains("CANCEL", na=False)].copy()
    completed_sales["Order Price"] = pd.to_numeric(completed_sales["Order Price"], errors="coerce").fillna(0)

    # -----------------------------------
    # 4. BUSINESS OVERVIEW (KPIs)
    # -----------------------------------
    st.subheader("📊 Business Overview")
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("Total Orders", sales[order_id_col].nunique())
    kpi2.metric("✅ Completed", completed_sales[order_id_col].nunique())
    kpi3.metric("❌ Cancelled", cancelled_orders[order_id_col].nunique())
    kpi4.metric("🛒 Units Sold", len(completed_sales))
    kpi5.metric("💰 Net Revenue", f"₹{completed_sales['Order Price'].sum():,.0f}")

    # -----------------------------------
    # 5. TABS WITH ENHANCED VISUALS
    # -----------------------------------
    tab1, tab2, tab3, tab4 = st.tabs(["📦 Inventory Health", "🛒 Sales Performance", "❌ Cancel Report", "📈 Analytics"])

    with tab1:
        sku_sales = completed_sales.groupby("Final SKU").size().reset_index(name="Total Sold")
        inventory = inv[["Sku Code", "Available (ATP)"]].rename(columns={"Sku Code": "SKU"})
        
        # Merge Logic
        data = pd.merge(sku_sales.rename(columns={"Final SKU": "SKU"}), inventory, on="SKU", how="outer").fillna(0)
        data["Stock To Order"] = (data["Total Sold"] - data["Available (ATP)"]).clip(lower=0)
        
        col_inv1, col_inv2 = st.columns(2)
        with col_inv1:
            st.markdown("#### 🚨 Top Stock to Order")
            st.dataframe(data[data["Stock To Order"] > 0].sort_values("Stock To Order", ascending=False), use_container_width=True)
        with col_inv2:
            st.markdown("#### 🧊 Dead Stock (No Sales, High Stock)")
            dead_stock = data[(data["Total Sold"] == 0) & (data["Available (ATP)" ] > 0)]
            st.dataframe(dead_stock.sort_values("Available (ATP)", ascending=False), use_container_width=True)

    # =====================================================
    # 🛒 SALES PERFORMANCE TAB (UPDATED)
    # =====================================================
    with tab2:
        st.subheader("🔥 Sales Performance Breakdown")
        
        # 1. Visual Charts Row
        c_sales1, c_sales2 = st.columns(2)
        
        with c_sales1:
            channel_data = completed_sales.groupby("Channel").size().reset_index(name="Units")
            fig_chan = px.pie(
                channel_data, 
                values="Units", 
                names="Channel", 
                title="Unit Distribution by Channel", 
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            st.plotly_chart(fig_chan, use_container_width=True)
            
        with c_sales2:
            top_skus = sku_sales.sort_values("Total Sold", ascending=False).head(10)
            fig_sku = px.bar(
                top_skus, 
                x="Total Sold", 
                y="Final SKU", 
                orientation='h', 
                title="Top 10 Best Selling SKUs",
                color="Total Sold",
                color_continuous_scale='Blues'
            )
            fig_sku.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_sku, use_container_width=True)

        st.markdown("---")
        
        # 2. Detailed Quantity Table
        st.subheader("📋 Detailed SKU Sales Quantities")
        
        # We can also add Revenue here since it's helpful
        sku_qty_val = completed_sales.groupby("Final SKU").agg(
            Total_Units=('Final SKU', 'count'),
            Total_Revenue=('Order Price', 'sum')
        ).sort_values("Total_Units", ascending=False).reset_index()
        
        # Rename for clarity
        sku_qty_val.rename(columns={"Final SKU": "Sku Code", "Total_Units": "Quantity Sold"}, inplace=True)

        # Using st.dataframe allows the user to search (Ctrl+F) and sort easily
        st.dataframe(
            sku_qty_val,
            use_container_width=True,
            column_config={
                "Quantity Sold": st.column_config.NumberColumn("Quantity Sold", help="Total units sold across all channels"),
                "Total_Revenue": st.column_config.NumberColumn("Revenue (₹)", format="₹%d"),
                "Sku Code": "Product SKU"
            },
            hide_index=True
        )

        # 3. Channel Breakdown Table
        with st.expander("View Unit Sales per Channel"):
            channel_units = completed_sales.groupby("Channel").size().reset_index(name="Units Sold").sort_values("Units Sold", ascending=False)
            st.table(channel_units)

    with tab3:
        st.markdown("### ❌ Cancellation Breakdown")
        cancelled_sku_channel = cancelled_orders.pivot_table(index="Final SKU", columns="Channel", aggfunc="size", fill_value=0)
        st.dataframe(cancelled_sku_channel.style.background_gradient(cmap="Reds"), use_container_width=True)

    # =====================================================
    # 📊 ANALYSIS TAB (UPDATED)
    # =====================================================
    with tab4:
        st.subheader("📈 Daily Performance Analysis")

        # 1. Metric Selector for Chart
        metric_choice = st.segmented_control(
            "Select Chart Metric", 
            ["Sale Units", "Total Sale Price"], 
            default="Sale Units"
        )

        completed_sales["Order Date"] = completed_sales["Uniware Created At"].dt.date
        
        # Prepare Chart Data
        if metric_choice == "Sale Units":
            daily_plot = completed_sales.groupby("Order Date").size()
        else:
            daily_plot = completed_sales.groupby("Order Date")["Order Price"].sum()

        # Visual Chart
        fig_trend = px.area(daily_plot, title=f"Daily Trend: {metric_choice}", color_discrete_sequence=['#007bff'])
        st.plotly_chart(fig_trend, use_container_width=True)

        # 2. Daily Averages Section
        st.markdown("### 📊 Key Performance Averages")
        avg_units = completed_sales.groupby("Order Date").size().mean()
        avg_price = completed_sales.groupby("Order Date")["Order Price"].sum().mean()
        # Average Order Value (AOV) = Total Revenue / Number of Unique Orders
        total_rev_sum = completed_sales["Order Price"].sum()
        unique_order_count = completed_sales[order_id_col].nunique()
        aov = total_rev_sum / unique_order_count if unique_order_count > 0 else 0

        a1, a2, a3 = st.columns(3)
        a1.metric("Avg Sale Units / Day", f"{avg_units:.1f}")
        a2.metric("Avg Sales Value / Day", f"₹{avg_price:,.0f}")
        a3.metric("Avg Order Value (AOV)", f"₹{aov:,.0f}")

        # 3. Channel Daily Data Table
        st.markdown("---")
        st.subheader("📋 Daily Sales Data by Channel")
        
        # Create a detailed pivot table for Channel x Date
        daily_channel_table = completed_sales.pivot_table(
            index="Order Date",
            columns="Channel",
            aggfunc="size",
            fill_value=0
        )
        
        # Add Total Units and Total Revenue columns
        daily_channel_table["Total Units"] = daily_channel_table.sum(axis=1)
        daily_rev = completed_sales.groupby("Order Date")["Order Price"].sum()
        daily_channel_table["Total Revenue (₹)"] = daily_rev

        # Style the table for readability
        st.dataframe(
            daily_channel_table.sort_index(ascending=False).reset_index(),
            use_container_width=True,
            column_config={
                "Total Revenue (₹)": st.column_config.NumberColumn(format="₹%d"),
                "Order Date": st.column_config.DateColumn("Date")
            }
        )

        # 4. SKU Performance Table (Values)
        st.subheader("📄 SKU Value Contribution")
        sku_value_table = completed_sales.groupby("Final SKU").agg(
            Units_Sold=('Final SKU', 'count'),
            Total_Revenue=('Order Price', 'sum')
        ).sort_values("Total_Revenue", ascending=False).reset_index()
        
        st.dataframe(sku_value_table, use_container_width=True, column_config={
            "Total_Revenue": st.column_config.NumberColumn(format="₹%d")
        })
else:
    st.info("💡 Please upload both UNIWARE files to unlock the dashboard.")