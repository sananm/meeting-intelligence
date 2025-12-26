'use client';

import { useState, useEffect } from 'react';
import { Upload, Search, Mic, FileVideo, Clock, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';

interface Meeting {
  id: string;
  title: string;
  status: string;
  duration_seconds: number | null;
}

interface SearchResult {
  meeting_id: string;
  meeting_title: string;
  chunk_content: string;
  start_time: number | null;
  end_time: number | null;
  similarity: number;
}

const statusConfig: Record<string, { icon: React.ReactNode; color: string; text: string }> = {
  pending: { icon: <Clock className="h-4 w-4" />, color: 'text-yellow-600 bg-yellow-50', text: 'Pending' },
  processing: { icon: <Loader2 className="h-4 w-4 animate-spin" />, color: 'text-blue-600 bg-blue-50', text: 'Processing' },
  transcribed: { icon: <Loader2 className="h-4 w-4 animate-spin" />, color: 'text-blue-600 bg-blue-50', text: 'Analyzing' },
  ready: { icon: <CheckCircle className="h-4 w-4" />, color: 'text-green-600 bg-green-50', text: 'Ready' },
  error: { icon: <AlertCircle className="h-4 w-4" />, color: 'text-red-600 bg-red-50', text: 'Error' },
};

export default function Home() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');

  // Fetch meetings on load and periodically
  useEffect(() => {
    fetchMeetings();
    const interval = setInterval(fetchMeetings, 5000); // Poll every 5s
    return () => clearInterval(interval);
  }, []);

  const fetchMeetings = async () => {
    try {
      const res = await fetch('/api/meetings');
      if (res.ok) {
        const data = await res.json();
        setMeetings(data);
      }
    } catch (error) {
      console.error('Error fetching meetings:', error);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadProgress('Uploading...');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', file.name.replace(/\.[^/.]+$/, ''));

    try {
      const res = await fetch('/api/meetings/upload', {
        method: 'POST',
        body: formData,
      });

      if (res.ok) {
        setUploadProgress('Upload complete! Processing...');
        fetchMeetings();
        setTimeout(() => {
          setIsUploading(false);
          setUploadProgress('');
        }, 2000);
      } else {
        const error = await res.json();
        setUploadProgress(`Error: ${error.detail}`);
        setTimeout(() => {
          setIsUploading(false);
          setUploadProgress('');
        }, 3000);
      }
    } catch (error) {
      setUploadProgress('Upload failed');
      setTimeout(() => {
        setIsUploading(false);
        setUploadProgress('');
      }, 3000);
    }

    // Reset file input
    e.target.value = '';
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    try {
      const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery, limit: 10 }),
      });

      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.results);
      }
    } catch (error) {
      console.error('Search error:', error);
    }
    setIsSearching(false);
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTime = (seconds: number | null) => {
    if (seconds === null) return '';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
      {/* Upload Section */}
      <div className="mb-8">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Upload Meeting Recording</h2>
          <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors">
            <div className="flex flex-col items-center justify-center pt-5 pb-6">
              {isUploading ? (
                <>
                  <Loader2 className="h-10 w-10 text-blue-500 animate-spin mb-2" />
                  <p className="text-sm text-gray-600">{uploadProgress}</p>
                </>
              ) : (
                <>
                  <Upload className="h-10 w-10 text-gray-400 mb-2" />
                  <p className="text-sm text-gray-600">
                    <span className="font-semibold text-blue-600">Click to upload</span> or drag and drop
                  </p>
                  <p className="text-xs text-gray-500 mt-1">MP3, WAV, MP4, MOV, WebM (max 500MB)</p>
                </>
              )}
            </div>
            <input
              type="file"
              className="hidden"
              accept="audio/*,video/*"
              onChange={handleUpload}
              disabled={isUploading}
            />
          </label>
        </div>
      </div>

      {/* Search Section */}
      <div className="mb-8">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold mb-4">Search Meetings</h2>
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search across all meetings..."
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <button
              type="submit"
              disabled={isSearching}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
            >
              {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Search
            </button>
          </form>

          {/* Search Results */}
          {searchResults.length > 0 && (
            <div className="mt-4 space-y-3">
              <h3 className="text-sm font-medium text-gray-700">Results</h3>
              {searchResults.map((result, idx) => (
                <a
                  key={idx}
                  href={`/meetings/${result.meeting_id}`}
                  className="block p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-gray-900">{result.meeting_title}</span>
                    <span className="text-xs text-gray-500">
                      {result.start_time !== null && `${formatTime(result.start_time)}`}
                      {result.similarity && ` • ${(result.similarity * 100).toFixed(0)}% match`}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 line-clamp-2">{result.chunk_content}</p>
                </a>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Meetings List */}
      <div>
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b">
            <h2 className="text-lg font-semibold">Your Meetings</h2>
          </div>
          {meetings.length === 0 ? (
            <div className="p-8 text-center text-gray-500">
              <Mic className="h-12 w-12 mx-auto mb-3 text-gray-300" />
              <p>No meetings yet. Upload a recording to get started.</p>
            </div>
          ) : (
            <ul className="divide-y">
              {meetings.map((meeting) => {
                const status = statusConfig[meeting.status] || statusConfig.pending;
                return (
                  <li key={meeting.id}>
                    <a
                      href={`/meetings/${meeting.id}`}
                      className="flex items-center justify-between px-6 py-4 hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <FileVideo className="h-5 w-5 text-gray-400" />
                        <div>
                          <p className="font-medium text-gray-900">{meeting.title}</p>
                          <p className="text-sm text-gray-500">
                            Duration: {formatDuration(meeting.duration_seconds)}
                          </p>
                        </div>
                      </div>
                      <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${status.color}`}>
                        {status.icon}
                        {status.text}
                      </span>
                    </a>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
