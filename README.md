# Scope vs Completed - Jira History Analysis

A sophisticated Streamlit web application that analyzes Jira project data to visualize **Scope** (cumulative story points added over time) vs **Completed** (cumulative story points completed over time). Built specifically for epic PL-54667 data analysis with real-time filtering, precise axis controls, and comprehensive export capabilities.

![App Screenshot](https://via.placeholder.com/800x400/1f77b4/ffffff?text=Scope+vs+Completed+Chart)

## 🎯 Key Features

### 🔐 **Secure Access**
- **Password protection**: Secure authentication system using bcrypt
- **Session management**: Browser-based authentication with logout functionality
- **Environment configuration**: Simple setup via environment variables

### 📊 **Precise Visualization**
- **Strict axis locks**: X-axis locked to max Due date, Y-axis locked to max Scope
- **Interactive charts** with hover details showing day-over-day deltas
- **Real-time filtering** with <1s recompute performance for 2k+ issues
- **Responsive design** that works on all screen sizes

### 🔍 **Advanced Filtering**
- **JQL query support** for flexible data fetching
- **Multi-select filters**: Labels, Components, Epics, Assignees
- **Smart exclusions**: Zombie issues, missing data points
- **Date range controls** with fallback logic

### 📈 **Rich Analytics**
- **KPI dashboard**: Max Scope, Completed %, Issue counts
- **Daily series analysis** with delta calculations
- **Issue-level summaries** with complete metadata
- **Validation reports** with warnings and insights

### 💾 **Export Everything**
- **CSV/JSON downloads** for both daily series and issue summaries
- **PNG chart export** with axis locks preserved
- **Configuration sharing** via JSON export

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Access to Jira instance (or use included golden dataset)
- MCP Atlassian server (optional for live data) OR local Jira credentials

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd burndown

# Install dependencies
pip install -r requirements.txt

# Run the application
streamlit run app.py
```

### Configuration Options

#### Option 1: Using Golden Dataset (No Setup Required)
The application includes a curated golden dataset that works out of the box for testing and demonstration purposes.

#### Option 2: MCP Atlassian Server (Preferred for Live Data)
Configure the MCP Atlassian server for real-time Jira data access through the MCP protocol.

#### Option 3: Direct Jira Access (Self-Contained Fallback)
Set up environment variables for direct Jira API access:

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your Jira credentials
JIRA_URL=https://your-instance.atlassian.net
JIRA_USERNAME=your.email@company.com  
JIRA_API_TOKEN=your-api-token
```

The application will automatically detect available connection methods and use the best option available:
1. MCP Server (if configured)
2. Local Jira fallback (if credentials provided)
3. Golden dataset (always available)

### Authentication Setup

**Important**: The application now requires authentication. Set up your password before first use:

```bash
# Edit .env file and set your password
APP_PASSWORD=MySecurePassword123!
```

Replace `MySecurePassword123!` with a strong, unique password. See [AUTH_README.md](AUTH_README.md) for detailed authentication documentation.

### First Time Setup

1. **Set authentication**: Configure `APP_PASSWORD` in your `.env` file
2. **Launch the app**: `streamlit run app.py`
3. **Login**: Enter your configured password when prompted
4. **Use golden dataset**: Click "Fetch / Refresh" (uses PL-54667 epic data by default)
5. **Explore the data**: Use filters in the sidebar to refine your analysis
6. **Export results**: Download charts and data using the export buttons

## 📋 Golden Dataset

The application includes a curated golden dataset based on **real Jira epic PL-54667** data:

- **22 issues** from the Layout Engine project
- **Mixed statuses**: Done, In Progress, To Do, etc.
- **Story points range**: 2-21 points per issue
- **Date range**: May 2025 - December 2025
- **Multiple assignees**: frontend.dev1, backend.dev1, qa.dev1, etc.

### Golden Dataset Highlights

- **Total Scope**: 139 story points
- **Completed Stories**: 11 issues (81 points)
- **In Progress**: 5 issues (58 points remaining)
- **Coverage**: Frontend, Backend, QA components

## 🏗️ Architecture

### Core Components

```
app.py              # Main Streamlit application
models.py           # Pydantic data models and validation
fetch.py            # Jira data fetching via MCP
transform.py        # Data filtering and computation engine
ui_helpers.py       # UI components and chart creation
golden_dataset.json # Test data based on PL-54667
```

### Key Algorithms

1. **Scope Calculation**: `Σ story_points where created_day ≤ current_date`
2. **Completed Calculation**: `Σ story_points where done_day ≤ current_date`
3. **Domain Detection**: Smart fallback logic for missing due dates
4. **Filter Chain**: Multi-stage filtering with performance optimization

## 🎮 Usage Guide

### Basic Workflow

1. **Configure Data Source**
   - Update JQL query in sidebar
   - Set timezone (default: America/Toronto)
   - Enable caching for performance

2. **Set Time Domain**
   - Override start date (t0) if needed
   - Choose fallback for end date (t1)
   - Define "Done" statuses for your workflow

3. **Apply Filters**
   - Select specific labels, components, epics
   - Exclude problematic issues
   - Toggle sub-task inclusion

4. **Analyze Results**
   - Review KPI metrics
   - Examine interactive chart
   - Export data and visualizations

### Advanced Features

#### Validation Mode
```python
# Enable in sidebar Advanced section
config.show_validation = True
```
Shows detailed metrics, warnings, and data quality insights.

#### Intermediate Tables
```python
# Enable in sidebar Advanced section
config.show_intermediate = True
```
Displays raw vs filtered issue counts and processing details.

#### Custom JQL Queries
```sql
-- Example: Focus on specific components
project = PL AND component in ("Frontend", "Backend") AND created >= "2025-01-01"

-- Example: Epic-specific analysis
"Epic Link" = PL-54667 AND issuetype != Epic

-- Example: Team-specific view
assignee in ("john.doe", "jane.smith") AND status changed TO "Done" DURING ("2025-01-01", "2025-12-31")
```

## 🔧 Configuration

### Environment Variables
```bash
# Optional: For live Jira data
JIRA_URL=https://your-instance.atlassian.net
JIRA_USERNAME=your.email@company.com
JIRA_API_TOKEN=your-api-token
```

### App Configuration
All settings are available in the sidebar:

- **Data Source**: JQL, timezone, caching
- **Domain**: Date overrides, fallback logic
- **Filters**: Exclusions, field filters
- **Display**: Validation, intermediate data

## 📊 Acceptance Criteria ✅

### ✅ UI Requirements Met
- [x] Strict axis locks (X: max Due date, Y: max Scope)
- [x] Real-time filtering (<1s for 2k issues)
- [x] Hover details with day-over-day deltas
- [x] Exclusion flows with immediate feedback
- [x] Fallback disclosure for missing due dates
- [x] CSV/JSON/PNG exports match screen data
- [x] Empty states with actionable guidance

### ✅ Data Accuracy Validated
- [x] Scope calculation: cumulative story points by created date
- [x] Completed calculation: cumulative done points by completion date  
- [x] Time domain: t0 (min created) to t1 (max due or fallback)
- [x] Filtering: zombie exclusion, missing data handling
- [x] Delta computation: day-over-day changes

### ✅ Performance Targets Met
- [x] Sub-second recomputation after filter changes
- [x] Efficient data caching and state management
- [x] Responsive UI across screen sizes
- [x] Memory-efficient handling of large datasets

## 🧪 Testing

### Manual Test Scenarios

1. **Golden Dataset Validation**
   ```bash
   # Run app with golden dataset
   streamlit run app.py
   # Verify: 139 total scope, 81 completed, 58.3% complete
   ```

2. **Filter Testing**
   - Toggle "Exclude Zombie" → verify count changes
   - Add specific issue keys to exclusion list
   - Change Done statuses → verify completion recalculation

3. **Export Validation**
   - Download daily CSV → verify date range matches chart
   - Export PNG → confirm axis locks preserved
   - JSON export → validate data integrity

### Expected Metrics (Golden Dataset)
- **Max Scope**: 139.0 story points
- **Completed @ t1**: 81.0 story points  
- **% Complete**: 58.3%
- **Included Issues**: 22
- **Date Range**: 2025-05-27 to 2025-12-31

## 🚦 Troubleshooting

### Common Issues

**No data displayed**
- Check JQL syntax in sidebar
- Verify date ranges are realistic
- Disable strict filters temporarily

**Chart appears empty**
- Ensure due dates exist or adjust t1 fallback
- Check if all issues are filtered out
- Review domain date range

**Performance issues**
- Enable caching in sidebar
- Reduce JQL result set size
- Check for data quality issues

### Debug Mode

Enable intermediate tables and validation report for detailed diagnostics:
```python
# In sidebar → Advanced
show_intermediate = True
show_validation = True
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes with tests
4. Submit a pull request with detailed description

### Development Setup

```bash
# Development dependencies
pip install -r requirements.txt

# Run with auto-reload
streamlit run app.py --server.runOnSave=true

# Code formatting
black *.py
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built for Method CRM's Layout Engine project (Epic PL-54667)
- Uses real Jira data via MCP Atlassian server
- Streamlit for rapid web app development
- Plotly for interactive visualizations

---

**Built with ❤️ for better project visibility and data-driven decisions**
