# backend/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Any
from enum import Enum
from datetime import datetime

class TimePeriod(str, Enum):
    WEEK = "7d"
    MONTH = "1mo"
    HALF_YEAR = "6mo"
    TWO_YEARS = "2y"
    FIVE_YEARS = "5y"
    TEN_YEARS = "10y"

app = FastAPI(title="Stock Analyzer API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def calculate_rsi(data: pd.Series, periods: int = 14) -> pd.Series:
    """Calculate Relative Strength Index"""
    # Calculate price changes
    delta = data.diff()
    
    # Separate gains and losses
    gains = delta.where(delta > 0, 0)
    losses = -delta.where(delta < 0, 0)
    
    # Calculate average gains and losses
    avg_gains = gains.rolling(window=periods).mean()
    avg_losses = losses.rolling(window=periods).mean()
    
    # Calculate RS and RSI
    rs = avg_gains / avg_losses
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculate Volume Weighted Average Price"""
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3
    volume = df['Volume']
    
    # Calculate VWAP
    vwap = (typical_price * volume).cumsum() / volume.cumsum()
    
    return vwap

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all technical indicators"""
    try:
        # Print data info for debugging
        print(f"Calculating indicators for {len(df)} data points")
        
        # Moving Averages (using adjusted close if available, otherwise close)
        df['50_MA'] = df['Close'].rolling(window=50, min_periods=1).mean()
        df['200_MA'] = df['Close'].rolling(window=200, min_periods=1).mean()
        
        # RSI
        df['RSI'] = calculate_rsi(df['Close'])
        
        # VWAP
        df['VWAP'] = calculate_vwap(df)
        
        # Print sample calculations for verification
        print("\nSample calculations for last data point:")
        print(f"Close: {df['Close'].iloc[-1]:.2f}")
        print(f"50 MA: {df['50_MA'].iloc[-1]:.2f}")
        print(f"200 MA: {df['200_MA'].iloc[-1]:.2f}")
        print(f"RSI: {df['RSI'].iloc[-1]:.2f}")
        print(f"VWAP: {df['VWAP'].iloc[-1]:.2f}")
        
        return df
        
    except Exception as e:
        print(f"Error in calculate_indicators: {str(e)}")
        raise

def prepare_response(df: pd.DataFrame, stock_info: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare API response with all calculated data"""
    try:
        # Get latest values
        latest_price = float(df['Close'].iloc[-1])
        latest_50ma = float(df['50_MA'].iloc[-1])
        latest_200ma = float(df['200_MA'].iloc[-1])
        latest_rsi = float(df['RSI'].iloc[-1])
        latest_vwap = float(df['VWAP'].iloc[-1])
        
        return {
            "metadata": {
                "ticker": stock_info.get('symbol', ''),
                "company_name": stock_info.get('longName', ''),
                "sector": stock_info.get('sector', 'N/A'),
                "industry": stock_info.get('industry', 'N/A'),
                "data_points": len(df),
                "start_date": df.index[0].strftime('%Y-%m-%d'),
                "end_date": df.index[-1].strftime('%Y-%m-%d')
            },
            "timeseries": {
                "dates": df.index.strftime('%Y-%m-%d').tolist(),
                "price": df['Close'].tolist(),
                "volume": df['Volume'].tolist(),
                "fifty_ma": df['50_MA'].tolist(),
                "twohundred_ma": df['200_MA'].tolist(),
                "rsi": df['RSI'].tolist(),
                "vwap": df['VWAP'].tolist()
            },
            "analysis": {
                "moving_averages": {
                    "latest_price": latest_price,
                    "latest_50ma": latest_50ma,
                    "latest_200ma": latest_200ma,
                    "is_golden_cross": latest_50ma > latest_200ma,
                    "price_above_50ma": latest_price > latest_50ma,
                    "price_above_200ma": latest_price > latest_200ma
                },
                "rsi": {
                    "current_rsi": latest_rsi,
                    "is_overbought": latest_rsi > 70,
                    "is_oversold": latest_rsi < 30
                },
                "vwap": {
                    "current_vwap": latest_vwap,
                    "price_above_vwap": latest_price > latest_vwap
                }
            }
        }
    except Exception as e:
        print(f"Error in prepare_response: {str(e)}")
        raise

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Stock Analyzer API is running",
        "version": "1.0.0",
        "available_periods": [period.value for period in TimePeriod]
    }

@app.get("/api/stock/{ticker}")
async def get_stock_data(
    ticker: str,
    period: TimePeriod = TimePeriod.MONTH
) -> Dict[str, Any]:
    """Main endpoint to get stock analysis"""
    try:
        print(f"\nProcessing request for {ticker} with period {period.value}")
        
        # Download data
        stock = yf.Ticker(ticker)
        df = stock.history(period=period.value, interval="1d")
        
        if df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for ticker {ticker}"
            )
        
        # Get stock info
        try:
            stock_info = stock.info
        except:
            print(f"Warning: Could not fetch info for {ticker}")
            stock_info = {"symbol": ticker}
        
        # Calculate indicators
        df = calculate_indicators(df)
        
        # Prepare response
        response_data = prepare_response(df, stock_info)
        
        return response_data
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error processing {ticker}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing request: {str(e)}"
        )

@app.get("/api/debug/{ticker}")
async def debug_stock_data(ticker: str):
    """Debug endpoint to validate calculations"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1mo", interval="1d")
        df = calculate_indicators(df)
        
        # Return last 5 days of data for verification
        return {
            "last_5_days": df.tail(5).to_dict(orient='records'),
            "calculations_sample": {
                "close": float(df['Close'].iloc[-1]),
                "50_ma": float(df['50_MA'].iloc[-1]),
                "200_ma": float(df['200_MA'].iloc[-1]),
                "rsi": float(df['RSI'].iloc[-1]),
                "vwap": float(df['VWAP'].iloc[-1])
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)