'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Clock,
  CheckCircle,
  AlertCircle,
  Loader2,
  FileText,
  ListChecks,
  Tags,
  Search,
  Trash2,
  Pencil,
  Check,
  X,
} from 'lucide-react';

interface Meeting {
  id: string;
  title: string;
  status: string;
  duration_seconds: number | null;
  transcript: {
    content: string;
    speaker_labels: Array<{
      start: number;
      end: number;
      text: string;
      speaker: string | null;
    }> | null;
    language: string | null;
  } | null;
  insights: {
    summary: string | null;
    action_items: Array<{ text: string; assignee: string | null; due_date: string | null }> | null;
    key_topics: string[] | null;
  } | null;
}

interface SearchResult {
  chunk_content: string;
  start_time: number | null;
  end_time: number | null;
  similarity: number;
}

export default function MeetingPage() {
  const params = useParams();
  const router = useRouter();
  const meetingId = params.id as string;

  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'transcript' | 'summary' | 'actions'>('transcript');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editTitle, setEditTitle] = useState('');

  useEffect(() => {
    fetchMeeting();
    // Poll while processing
    const interval = setInterval(() => {
      if (meeting?.status && !['ready', 'error'].includes(meeting.status)) {
        fetchMeeting();
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [meetingId, meeting?.status]);

  const fetchMeeting = async () => {
    try {
      const res = await fetch(`/api/meetings/${meetingId}`);
      if (res.ok) {
        const data = await res.json();
        setMeeting(data);
      }
    } catch (error) {
      console.error('Error fetching meeting:', error);
    }
    setLoading(false);
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    try {
      const res = await fetch(`/api/search/meetings/${meetingId}?query=${encodeURIComponent(searchQuery)}&limit=5`);
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.results);
      }
    } catch (error) {
      console.error('Search error:', error);
    }
    setIsSearching(false);
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this recording? This action cannot be undone.')) return;

    setIsDeleting(true);
    try {
      const res = await fetch(`/api/meetings/${meetingId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        router.push('/');
      } else {
        alert('Failed to delete recording');
        setIsDeleting(false);
      }
    } catch (error) {
      console.error('Delete error:', error);
      alert('Failed to delete recording');
      setIsDeleting(false);
    }
  };

  const startEditingTitle = () => {
    if (meeting) {
      setEditTitle(meeting.title);
      setIsEditingTitle(true);
    }
  };

  const cancelEditingTitle = () => {
    setIsEditingTitle(false);
    setEditTitle('');
  };

  const handleRename = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editTitle.trim() || !meeting) return;

    try {
      const res = await fetch(`/api/meetings/${meetingId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: editTitle.trim() }),
      });

      if (res.ok) {
        setMeeting({ ...meeting, title: editTitle.trim() });
      } else {
        alert('Failed to rename recording');
      }
    } catch (error) {
      console.error('Rename error:', error);
      alert('Failed to rename recording');
    }

    setIsEditingTitle(false);
    setEditTitle('');
  };

  const formatTime = (seconds: number | null) => {
    if (seconds === null) return '';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (!meeting) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 mx-auto text-red-500 mb-4" />
          <h1 className="text-xl font-semibold">Meeting not found</h1>
          <a href="/" className="text-blue-600 hover:underline mt-2 inline-block">
            Go back home
          </a>
        </div>
      </div>
    );
  }

  const isProcessing = ['pending', 'processing', 'transcribed'].includes(meeting.status);

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <a href="/" className="inline-flex items-center text-gray-600 hover:text-gray-900 mb-4">
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back to meetings
        </a>
        <div className="flex items-start justify-between">
          <div>
            {isEditingTitle ? (
              <form onSubmit={handleRename} className="flex items-center gap-2">
                <input
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="text-2xl font-bold text-gray-900 px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  autoFocus
                />
                <button
                  type="submit"
                  className="p-1.5 text-green-600 hover:bg-green-50 rounded"
                  title="Save"
                >
                  <Check className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  onClick={cancelEditingTitle}
                  className="p-1.5 text-gray-400 hover:bg-gray-100 rounded"
                  title="Cancel"
                >
                  <X className="h-5 w-5" />
                </button>
              </form>
            ) : (
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold text-gray-900">{meeting.title}</h1>
                <button
                  onClick={startEditingTitle}
                  className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                  title="Rename"
                >
                  <Pencil className="h-4 w-4" />
                </button>
              </div>
            )}
            <p className="text-gray-500 mt-1">
              Duration: {formatDuration(meeting.duration_seconds)}
              {meeting.transcript?.language && ` • Language: ${meeting.transcript.language.toUpperCase()}`}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={meeting.status} />
            <button
              onClick={handleDelete}
              disabled={isDeleting}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
              title="Delete recording"
            >
              {isDeleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Delete
            </button>
          </div>
        </div>
      </div>

      {/* Processing State */}
      {isProcessing && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
          <div className="flex items-center gap-3">
            <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
            <div>
              <p className="font-medium text-blue-900">Processing your meeting...</p>
              <p className="text-sm text-blue-700">
                {meeting.status === 'pending' && 'Waiting to start transcription'}
                {meeting.status === 'processing' && 'Transcribing audio'}
                {meeting.status === 'transcribed' && 'Generating summary and insights'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Search within meeting */}
      {meeting.status === 'ready' && (
        <div className="bg-white rounded-lg shadow p-4 mb-6">
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search within this meeting..."
                className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <button
              type="submit"
              disabled={isSearching}
              className="px-3 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-50 text-sm"
            >
              {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Search'}
            </button>
          </form>

          {searchResults.length > 0 && (
            <div className="mt-3 space-y-2">
              {searchResults.map((result, idx) => (
                <div key={idx} className="p-2 bg-yellow-50 rounded border border-yellow-200">
                  <div className="text-xs text-yellow-700 mb-1">
                    {result.start_time !== null && `At ${formatTime(result.start_time)}`}
                    {` • ${(result.similarity * 100).toFixed(0)}% match`}
                  </div>
                  <p className="text-sm text-gray-800">{result.chunk_content}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tabs */}
      {meeting.status === 'ready' && (
        <>
          <div className="border-b mb-6">
            <nav className="flex gap-6">
              <TabButton
                active={activeTab === 'transcript'}
                onClick={() => setActiveTab('transcript')}
                icon={<FileText className="h-4 w-4" />}
                label="Transcript"
              />
              <TabButton
                active={activeTab === 'summary'}
                onClick={() => setActiveTab('summary')}
                icon={<Tags className="h-4 w-4" />}
                label="Summary"
              />
              <TabButton
                active={activeTab === 'actions'}
                onClick={() => setActiveTab('actions')}
                icon={<ListChecks className="h-4 w-4" />}
                label="Action Items"
                count={meeting.insights?.action_items?.length}
              />
            </nav>
          </div>

          {/* Tab Content */}
          <div className="bg-white rounded-lg shadow">
            {activeTab === 'transcript' && (
              <div className="p-6">
                <h2 className="text-lg font-semibold mb-4">Full Transcript</h2>
                {meeting.transcript?.speaker_labels ? (
                  <div className="space-y-3">
                    {meeting.transcript.speaker_labels.map((segment, idx) => (
                      <div key={idx} className="flex gap-3">
                        <span className="text-xs text-gray-400 w-12 flex-shrink-0 pt-1">
                          {formatTime(segment.start)}
                        </span>
                        <p className="text-gray-800">{segment.text}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-800 whitespace-pre-wrap">
                    {meeting.transcript?.content || 'No transcript available'}
                  </p>
                )}
              </div>
            )}

            {activeTab === 'summary' && (
              <div className="p-6">
                <h2 className="text-lg font-semibold mb-4">Meeting Summary</h2>
                <p className="text-gray-800 mb-6">
                  {meeting.insights?.summary || 'No summary available'}
                </p>

                {meeting.insights?.key_topics && meeting.insights.key_topics.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 mb-2">Key Topics</h3>
                    <div className="flex flex-wrap gap-2">
                      {meeting.insights.key_topics.map((topic, idx) => (
                        <span
                          key={idx}
                          className="px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-sm"
                        >
                          {topic}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'actions' && (
              <div className="p-6">
                <h2 className="text-lg font-semibold mb-4">Action Items</h2>
                {meeting.insights?.action_items && meeting.insights.action_items.length > 0 ? (
                  <ul className="space-y-3">
                    {meeting.insights.action_items.map((item, idx) => (
                      <li key={idx} className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          className="mt-1 h-4 w-4 rounded border-gray-300"
                        />
                        <div>
                          <p className="text-gray-800">{item.text}</p>
                          {(item.assignee || item.due_date) && (
                            <p className="text-sm text-gray-500 mt-1">
                              {item.assignee && `Assigned to: ${item.assignee}`}
                              {item.assignee && item.due_date && ' • '}
                              {item.due_date && `Due: ${item.due_date}`}
                            </p>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-gray-500">No action items found in this meeting.</p>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { icon: React.ReactNode; color: string; text: string }> = {
    pending: { icon: <Clock className="h-4 w-4" />, color: 'text-yellow-600 bg-yellow-50', text: 'Pending' },
    processing: { icon: <Loader2 className="h-4 w-4 animate-spin" />, color: 'text-blue-600 bg-blue-50', text: 'Processing' },
    transcribed: { icon: <Loader2 className="h-4 w-4 animate-spin" />, color: 'text-blue-600 bg-blue-50', text: 'Analyzing' },
    ready: { icon: <CheckCircle className="h-4 w-4" />, color: 'text-green-600 bg-green-50', text: 'Ready' },
    error: { icon: <AlertCircle className="h-4 w-4" />, color: 'text-red-600 bg-red-50', text: 'Error' },
  };

  const { icon, color, text } = config[status] || config.pending;

  return (
    <span className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium ${color}`}>
      {icon}
      {text}
    </span>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  count?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 pb-3 border-b-2 transition-colors ${
        active
          ? 'border-blue-600 text-blue-600'
          : 'border-transparent text-gray-500 hover:text-gray-700'
      }`}
    >
      {icon}
      {label}
      {count !== undefined && count > 0 && (
        <span className="bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded-full">
          {count}
        </span>
      )}
    </button>
  );
}
