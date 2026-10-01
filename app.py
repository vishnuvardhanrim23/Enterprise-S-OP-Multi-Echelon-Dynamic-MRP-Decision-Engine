import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import norm
import io

# Set Page Config
st.set_page_config(
    page_title="Enterprise S&OP & MRP Decision Engine",
    page_icon="⚙️",
    layout="wide"
)

st.title("⚙️ Strategic Multi-Echelon S&OP & Automated MRP Engine")
st.caption("Industrial Engineering & Management | Production & Supply Chain Optimization Control Tower")

# ---------------------------------------------------------
# DATA GENERATION & CSV UPLOAD ENGINE
# ---------------------------------------------------------
@st.cache_data
def generate_base_data():
    np.random.seed(42)

    skus = [
        {'sku_id': 'FG-101', 'name': 'EV Motor Assembly', 'type': 'Finished Good', 'unit_cost': 45000, 'holding_cost_pct': 0.20, 'selling_price': 65000, 'target_service_level': 0.98},
        {'sku_id': 'FG-102', 'name': 'Transmission Gearbox', 'type': 'Finished Good', 'unit_cost': 32000, 'holding_cost_pct': 0.20, 'selling_price': 48000, 'target_service_level': 0.95},
        {'sku_id': 'COMP-01', 'name': 'Stator Core', 'type': 'Component', 'unit_cost': 8500, 'holding_cost_pct': 0.18, 'selling_price': 0, 'target_service_level': 0.98},
        {'sku_id': 'COMP-02', 'name': 'Rotor Shaft', 'type': 'Component', 'unit_cost': 6200, 'holding_cost_pct': 0.18, 'selling_price': 0, 'target_service_level': 0.98},
        {'sku_id': 'COMP-03', 'name': 'Helical Gear', 'type': 'Component', 'unit_cost': 4100, 'holding_cost_pct': 0.18, 'selling_price': 0, 'target_service_level': 0.95},
    ]
    sku_df = pd.DataFrame(skus)

    bom = [
        {'parent_sku': 'FG-101', 'child_sku': 'COMP-01', 'qty_required': 1},
        {'parent_sku': 'FG-101', 'child_sku': 'COMP-02', 'qty_required': 1},
        {'parent_sku': 'FG-102', 'child_sku': 'COMP-03', 'qty_required': 2},
    ]
    bom_df = pd.DataFrame(bom)

    suppliers = [
        {'child_sku': 'COMP-01', 'supplier_id': 'SUP-A', 'avg_lead_time_days': 14, 'lead_time_std_days': 3.5, 'moq': 50},
        {'child_sku': 'COMP-02', 'supplier_id': 'SUP-B', 'avg_lead_time_days': 10, 'lead_time_std_days': 2.0, 'moq': 100},
        {'child_sku': 'COMP-03', 'supplier_id': 'SUP-C', 'avg_lead_time_days': 21, 'lead_time_std_days': 5.0, 'moq': 200},
    ]
    supplier_df = pd.DataFrame(suppliers)

    dates = pd.date_range(start='2025-01-01', periods=365, freq='D')
    demand_records = []

    for date in dates:
        base_fg101 = 25 + int(5 * np.sin(date.dayofyear / 20)) + np.random.poisson(3)
        base_fg102 = 18 + int(4 * np.cos(date.dayofyear / 25)) + np.random.poisson(2)
        
        demand_records.append({'date': date, 'sku_id': 'FG-101', 'daily_demand': max(0, base_fg101)})
        demand_records.append({'date': date, 'sku_id': 'FG-102', 'daily_demand': max(0, base_fg102)})

    demand_df = pd.DataFrame(demand_records)
    return sku_df, bom_df, supplier_df, demand_df

# SIDEBAR: DATA SOURCE SELECTOR
st.sidebar.header("📁 Data Source Setup")
data_mode = st.sidebar.radio("Select Data Source:", ["Demo Synthetic Data", "Upload Enterprise CSVs"])

data_loaded = False

if data_mode == "Demo Synthetic Data":
    sku_df, bom_df, supplier_df, demand_df = generate_base_data()
    data_loaded = True
    st.sidebar.success("Loaded built-in demonstration dataset.")
else:
    st.sidebar.subheader("Upload Enterprise CSV Files")
    uploaded_skus = st.sidebar.file_uploader("1. SKU Master (skus.csv)", type=["csv"])
    uploaded_bom = st.sidebar.file_uploader("2. BOM Master (bom.csv)", type=["csv"])
    uploaded_suppliers = st.sidebar.file_uploader("3. Supplier Master (suppliers.csv)", type=["csv"])
    uploaded_demand = st.sidebar.file_uploader("4. Demand Log (demand.csv)", type=["csv"])

    if uploaded_skus and uploaded_bom and uploaded_suppliers and uploaded_demand:
        try:
            sku_df = pd.read_csv(uploaded_skus)
            bom_df = pd.read_csv(uploaded_bom)
            supplier_df = pd.read_csv(uploaded_suppliers)
            demand_df = pd.read_csv(uploaded_demand)
            data_loaded = True
            st.sidebar.success("All enterprise CSVs uploaded successfully!")
        except Exception as e:
            st.sidebar.error(f"Error parsing CSV files: {str(e)}")
    else:
        st.info(" Please upload all 4 required CSV files (`skus.csv`, `bom.csv`, `suppliers.csv`, `demand.csv`) in the sidebar to proceed, or switch to 'Demo Synthetic Data'.")

# ---------------------------------------------------------
# MAIN CALCULATION ENGINE
# ---------------------------------------------------------
if data_loaded:
    try:
        # Sidebar Parameter Controls
        st.sidebar.header("🎯 Scenario & Parameter Tuning")
        service_level_override = st.sidebar.slider("Global Target Service Level (%)", 80.0, 99.9, 98.0, 0.5) / 100.0
        lead_time_multiplier = st.sidebar.slider("Supplier Lead Time Volatility Factor", 0.5, 2.5, 1.0, 0.1)

        # 1. Aggregate Demand Stats
        demand_stats = demand_df.groupby('sku_id')['daily_demand'].agg(['mean', 'std']).reset_index()
        demand_stats.columns = ['sku_id', 'avg_daily_demand', 'std_daily_demand']
        demand_stats['std_daily_demand'] = demand_stats['std_daily_demand'].fillna(0)

        # 2. Derive Component Demand via BOM
        component_demand = []
        for _, row in bom_df.iterrows():
            parent_matches = demand_stats[demand_stats['sku_id'] == row['parent_sku']]
            if not parent_matches.empty:
                parent_stats = parent_matches.iloc[0]
                comp_avg = parent_stats['avg_daily_demand'] * row['qty_required']
                comp_std = parent_stats['std_daily_demand'] * row['qty_required']
                component_demand.append({
                    'sku_id': row['child_sku'],
                    'avg_daily_demand': comp_avg,
                    'std_daily_demand': comp_std
                })

        comp_demand_df = pd.DataFrame(component_demand)
        
        if not comp_demand_df.empty:
            all_demand_stats = pd.concat([demand_stats, comp_demand_df], ignore_index=True)
            # Combine duplicates if a component serves multiple parents
            all_demand_stats = all_demand_stats.groupby('sku_id').agg({'avg_daily_demand': 'sum', 'std_daily_demand': 'sum'}).reset_index()
        else:
            all_demand_stats = demand_stats

        # 3. Consolidate Master Analysis Table
        master_df = sku_df.merge(all_demand_stats, on='sku_id', how='left')
        master_df = master_df.merge(supplier_df, left_on='sku_id', right_on='child_sku', how='left')

        # Clean NaN defaults safely
        master_df['avg_lead_time_days'] = master_df['avg_lead_time_days'].fillna(5).astype(float)
        master_df['lead_time_std_days'] = (master_df['lead_time_std_days'].fillna(1.0) * lead_time_multiplier).astype(float)
        master_df['moq'] = master_df['moq'].fillna(10).astype(int)
        master_df['avg_daily_demand'] = master_df['avg_daily_demand'].fillna(0).astype(float)
        master_df['std_daily_demand'] = master_df['std_daily_demand'].fillna(0).astype(float)
        master_df['unit_cost'] = master_df['unit_cost'].fillna(0).astype(float)
        master_df['holding_cost_pct'] = master_df['holding_cost_pct'].fillna(0.20).astype(float)

        # Calculate Safety Stock & Reorder Points
        results = []
        for _, row in master_df.iterrows():
            d_bar = row['avg_daily_demand']
            sigma_d = row['std_daily_demand']
            L_bar = row['avg_lead_time_days']
            sigma_L = row['lead_time_std_days']
            unit_cost = row['unit_cost']
            holding_pct = row['holding_cost_pct']
            
            # Z-Score from target service level
            z = norm.ppf(service_level_override)
            
            # Dynamic Mathematical Safety Stock Equation
            ss_dynamic_val = (L_bar * (sigma_d**2)) + ((d_bar**2) * (sigma_L**2))
            ss_dynamic = z * np.sqrt(max(0, ss_dynamic_val))
            ss_dynamic = int(np.ceil(ss_dynamic))
            
            # Legacy Fixed Formula (15 Days Fixed Buffer)
            ss_legacy = int(np.ceil(15 * d_bar))
            
            # Reorder Point (ROP) = (Demand * LeadTime) + SafetyStock
            rop_dynamic = int(np.ceil((d_bar * L_bar) + ss_dynamic))
            rop_legacy = int(np.ceil((d_bar * L_bar) + ss_legacy))
            
            # Annual Holding Costs
            holding_cost_dynamic = ss_dynamic * unit_cost * holding_pct
            holding_cost_legacy = ss_legacy * unit_cost * holding_pct
            
            results.append({
                'SKU ID': row['sku_id'],
                'Name': row['name'],
                'Type': row['type'],
                'Avg Demand (Units/Day)': round(d_bar, 2),
                'Lead Time (Days)': L_bar,
                'Legacy SS (Units)': ss_legacy,
                'Dynamic SS (Units)': ss_dynamic,
                'Legacy ROP (Units)': rop_legacy,
                'Dynamic ROP (Units)': rop_dynamic,
                'Legacy Annual Holding Cost (₹)': round(holding_cost_legacy, 2),
                'Dynamic Annual Holding Cost (₹)': round(holding_cost_dynamic, 2),
                'Working Capital Savings (₹)': round(holding_cost_legacy - holding_cost_dynamic, 2)
            })

        res_df = pd.DataFrame(results)

        # ---------------------------------------------------------
        # INTERFACE & DASHBOARD TABS
        # ---------------------------------------------------------
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Executive ROI & Metrics", 
            "🧮 Inventory Policy Comparison", 
            "⚙️ Multi-Level BOM & MRP", 
            "📄 Automated Purchase Orders"
        ])

        # TAB 1: EXECUTIVE ROI
        with tab1:
            st.subheader("Working Capital & Inventory Efficiency Impact")
            
            total_legacy_cost = res_df['Legacy Annual Holding Cost (₹)'].sum()
            total_dynamic_cost = res_df['Dynamic Annual Holding Cost (₹)'].sum()
            total_savings = res_df['Working Capital Savings (₹)'].sum()
            pct_savings = (total_savings / total_legacy_cost * 100) if total_legacy_cost > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Legacy Holding Cost", f"₹{total_legacy_cost:,.2f}")
            col2.metric("Dynamic Holding Cost", f"₹{total_dynamic_cost:,.2f}")
            col3.metric("Annual Cost Reduction", f"₹{total_savings:,.2f}", delta=f"{pct_savings:.1f}% Savings")
            col4.metric("Target Service Level", f"{service_level_override*100:.1f}%")
            
            st.markdown("---")
            st.subheader("Holding Cost Comparison by Item")
            chart_data = res_df.set_index('SKU ID')[['Legacy Annual Holding Cost (₹)', 'Dynamic Annual Holding Cost (₹)']]
            st.bar_chart(chart_data)

        # TAB 2: DETAILED INVENTORY POLICY
        with tab2:
            st.subheader("Item-Level Safety Stock & Reorder Point (ROP) Breakdown")
            st.dataframe(res_df, use_container_width=True)
            st.info("💡 **Key Insight:** Legacy rules over-buffer predictable items while severely under-buffering long-lead-time components with high variance.")

        # TAB 3: BOM & MRP EXPLOSION
        with tab3:
            st.subheader("Bill of Materials (BOM) Requirements Explosion")
            
            fg_options = sku_df[sku_df['type'] == 'Finished Good']['sku_id'].unique()
            if len(fg_options) > 0:
                selected_fg = st.selectbox("Select Finished Good to Explode BOM:", fg_options)
                prod_qty = st.number_input("Target Production Quantity (Units):", min_value=1, value=100)
                
                sub_bom = bom_df[bom_df['parent_sku'] == selected_fg].copy()
                if not sub_bom.empty:
                    sub_bom = sub_bom.merge(sku_df[['sku_id', 'name', 'unit_cost']], left_on='child_sku', right_on='sku_id')
                    sub_bom['Gross Component Required'] = sub_bom['qty_required'] * prod_qty
                    sub_bom['Total Component Cost (₹)'] = sub_bom['Gross Component Required'] * sub_bom['unit_cost']
                    
                    st.table(sub_bom[['child_sku', 'name', 'qty_required', 'Gross Component Required', 'unit_cost', 'Total Component Cost (₹)']])
                else:
                    st.warning("No BOM components defined for this selected Finished Good.")
            else:
                st.warning("No Finished Goods found in the uploaded SKU dataset.")

        # TAB 4: AUTOMATED PO GENERATION
        with tab4:
            st.subheader("Automated Purchase Order (PO) Requisitions")
            st.markdown("Simulated PO generation based on current dynamic Reorder Point (ROP) triggers.")
            
            po_list = []
            comp_rows = res_df[res_df['Type'] == 'Component']
            
            if not comp_rows.empty:
                for _, row in comp_rows.iterrows():
                    simulated_current_stock = int(row['Dynamic ROP (Units)'] * 0.8)
                    reorder_qty = max(row['Dynamic ROP (Units)'] - simulated_current_stock, 50)
                    
                    po_list.append({
                        'PO Number': f"PO-2026-{np.random.randint(1000, 9999)}",
                        'Component SKU': row['SKU ID'],
                        'Component Name': row['Name'],
                        'Current Stock': simulated_current_stock,
                        'Dynamic ROP': row['Dynamic ROP (Units)'],
                        'Suggested Order Qty': reorder_qty,
                        'Status': 'RELEASED / PENDING SUPPLIER'
                    })
                
                po_df = pd.DataFrame(po_list)
                st.dataframe(po_df, use_container_width=True)
                
                # Export POs CSV
                csv_buffer = io.StringIO()
                po_df.to_csv(csv_buffer, index=False)
                st.download_button(
                    label="📥 Download Generated Purchase Orders (CSV)",
                    data=csv_buffer.getvalue(),
                    file_name="Automated_Purchase_Orders.csv",
                    mime="text/csv"
                )
            else:
                st.info("No Component SKUs available to generate Purchase Orders.")

    except Exception as err:
        st.error(f"An unexpected error occurred during execution: {str(err)}")
