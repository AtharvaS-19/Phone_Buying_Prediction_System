import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js/+esm'

const SUPABASE_URL = 'https://kbpswsbsttmbikhuipzg.supabase.co'
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImticHN3c2JzdHRtYmlraHVpcHpnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQwMjQ5NzYsImV4cCI6MjA4OTYwMDk3Nn0.TQLz8d42t_2tnYKXLzHo4Flw3bq1kbhIU_458Yf6ZNY'

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)