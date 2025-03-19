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

-- Create index on scheduled_time for efficient querying
CREATE INDEX IF NOT EXISTS idx_scheduled_calls_scheduled_time ON scheduled_calls(scheduled_time);

-- Create index on status for efficient querying
CREATE INDEX IF NOT EXISTS idx_scheduled_calls_status ON scheduled_calls(status);

-- Enable Row Level Security (RLS)
ALTER TABLE scheduled_calls ENABLE ROW LEVEL SECURITY;

-- Create policy to allow all operations (you may want to restrict this based on your needs)
CREATE POLICY "Allow all operations on scheduled_calls" ON scheduled_calls
    FOR ALL
    USING (true)
    WITH CHECK (true); 