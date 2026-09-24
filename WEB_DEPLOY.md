# US500 Research Terminal

Research-only Streamlit dashboard for the US500 Macro Intelligence repository.

## Streamlit secrets

```toml
GITHUB_TOKEN = "YOUR_GITHUB_TOKEN"
FRED_API_KEY = "YOUR_FRED_API_KEY"
US500_TICKER = "^GSPC"
```

`GITHUB_TOKEN` must be able to read Actions artifacts from the repository. The app discovers the latest non-expired artifact by artifact name, so it does not depend on hard-coded artifact IDs.

The dashboard does not generate trading signals, forecasts, execution instructions, position sizing, or directional recommendations.
