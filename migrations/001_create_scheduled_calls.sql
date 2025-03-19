-- Create scheduled_calls table
CREATE TABLE IF NOT EXISTS scheduled_calls (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
    scheduled_time TIMESTAMP WITH TIME ZONE NOT NULL,
    phone_number TEXT NOT NULL,
    status TEXT DEFAULT 'pending' NOT NULL,
    call_sid TEXT,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Create index on scheduled_time for faster queries
CREATE INDEX IF NOT EXISTS idx_scheduled_calls_scheduled_time ON scheduled_calls(scheduled_time);

-- Create index on status for faster queries
CREATE INDEX IF NOT EXISTS idx_scheduled_calls_status ON scheduled_calls(status);

-- Add RLS (Row Level Security) policies
ALTER TABLE scheduled_calls ENABLE ROW LEVEL SECURITY;

-- Allow all authenticated users to read scheduled calls
CREATE POLICY "Allow authenticated users to read scheduled calls"
    ON scheduled_calls FOR SELECT
    TO authenticated
    USING (true);

-- Allow all authenticated users to insert scheduled calls
CREATE POLICY "Allow authenticated users to insert scheduled calls"
    ON scheduled_calls FOR INSERT
    TO authenticated
    WITH CHECK (true);

-- Allow all authenticated users to update their own scheduled calls
CREATE POLICY "Allow authenticated users to update their own scheduled calls"
    ON scheduled_calls FOR UPDATE
    TO authenticated
    USING (true)
    WITH CHECK (true);

-- Allow all authenticated users to delete their own scheduled calls
CREATE POLICY "Allow authenticated users to delete their own scheduled calls"
    ON scheduled_calls FOR DELETE
    TO authenticated
    USING (true); 