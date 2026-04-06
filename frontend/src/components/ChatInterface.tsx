import React, { useState, useRef, useEffect } from 'react';
import { Send, User, Loader2, Paperclip, Sparkles, Image, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css';

const CHAT_LOADING_PHASES = [
  'Understanding your message…',
  'Gathering context and tools…',
  'Running the agent…',
  'Synthesizing an answer…',
];

const PDF_LOADING_PHASES = [
  'Receiving your file…',
  'Extracting text from PDF…',
  'Building embeddings…',
  'Indexing for search…',
];

const IMAGE_LOADING_PHASES = [
  'Receiving your image…',
  'Processing image content…',
  'Analyzing visual elements…',
  'Ready for response…',
];

interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
  reasoningTrace?: string;
  image?: string;
}

const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isUploadingPdf, setIsUploadingPdf] = useState(false);
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [loadingPhase, setLoadingPhase] = useState('');
  const [showAttachmentMenu, setShowAttachmentMenu] = useState(false);
  const [hasUploadedFile, setHasUploadedFile] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const attachmentMenuRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, isUploadingPdf, isUploadingImage, loadingPhase]);

  useEffect(() => {
    const fileAlreadyUploaded = messages.some(
      (m) =>
        m.role === 'user' &&
        (m.content.startsWith('Uploaded PDF:') ||
         m.content.startsWith('Uploaded image:') ||
         m.image)
    );
    if (fileAlreadyUploaded) {
      setHasUploadedFile(true);
    }
  }, [messages]);

  useEffect(() => {
    if (!isLoading && !isUploadingPdf && !isUploadingImage) {
      setLoadingPhase('');
      return;
    }
    let phases: string[];
    if (isUploadingPdf) {
      phases = PDF_LOADING_PHASES;
    } else if (isUploadingImage) {
      phases = IMAGE_LOADING_PHASES;
    } else {
      phases = CHAT_LOADING_PHASES;
    }
    let i = 0;
    setLoadingPhase(phases[0]);
    const id = window.setInterval(() => {
      i = (i + 1) % phases.length;
      setLoadingPhase(phases[i]);
    }, 2000);
    return () => window.clearInterval(id);
  }, [isLoading, isUploadingPdf, isUploadingImage]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (attachmentMenuRef.current && !attachmentMenuRef.current.contains(event.target as Node)) {
        setShowAttachmentMenu(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const apiBase = (process.env.REACT_APP_API_URL || '').replace(/\/$/, '');

  const uploadImage = async (file: File) => {
    if (!file.type.startsWith('image/')) {
      const err: Message = {
        id: Date.now().toString(),
        content: 'Please choose an image file.',
        role: 'assistant',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, err]);
      return;
    }

    setIsUploadingImage(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const url = `${apiBase}/upload/image`;
      const response = await fetch(url, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail =
          typeof data.detail === 'string'
            ? data.detail
            : Array.isArray(data.detail)
              ? data.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(' ')
              : 'Upload failed';
        throw new Error(detail || 'Upload failed');
      }

      const reader = new FileReader();
      reader.onloadend = () => {
        const userNote: Message = {
          id: Date.now().toString(),
          content: `Uploaded image: ${file.name}`,
          role: 'user',
          timestamp: new Date(),
          image: reader.result as string,
        };
        const assistantNote: Message = {
          id: (Date.now() + 1).toString(),
          content: `Image processed. ${data.message || 'You can ask questions about this image.'}`,
          role: 'assistant',
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, userNote, assistantNote]);
        setHasUploadedFile(true);
      };
      reader.readAsDataURL(file);
    } catch (error) {
      console.error('Image upload error:', error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content:
          error instanceof Error
            ? error.message
            : 'Could not upload the image. Is the backend running?',
        role: 'assistant',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsUploadingImage(false);
      if (imageInputRef.current) {
        imageInputRef.current.value = '';
      }
    }
  };

  const uploadPdf = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      const err: Message = {
        id: Date.now().toString(),
        content: 'Please choose a PDF file (.pdf).',
        role: 'assistant',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, err]);
      return;
    }

    setIsUploadingPdf(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const url = `${apiBase}/upload/pdf`;
      const response = await fetch(url, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail =
          typeof data.detail === 'string'
            ? data.detail
            : Array.isArray(data.detail)
              ? data.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(' ')
              : 'Upload failed';
        throw new Error(detail || 'Upload failed');
      }

      const userNote: Message = {
        id: Date.now().toString(),
        content: `Uploaded PDF: ${file.name}`,
        role: 'user',
        timestamp: new Date(),
      };
      const assistantNote: Message = {
        id: (Date.now() + 1).toString(),
        content: `PDF indexed. ${data.message || 'You can ask questions about this document.'}`,
        role: 'assistant',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userNote, assistantNote]);
      setHasUploadedFile(true);
    } catch (error) {
      console.error('PDF upload error:', error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content:
          error instanceof Error
            ? error.message
            : 'Could not upload the PDF. Is the backend running?',
        role: 'assistant',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsUploadingPdf(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handlePdfPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      void uploadPdf(file);
    }
  };

  const handleImagePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      void uploadImage(file);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading || isUploadingPdf || isUploadingImage) return;

    const text = input.trim();

    const userMessage: Message = {
      id: Date.now().toString(),
      content: text,
      role: 'user',
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const url = `${apiBase}/chat`;
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: text }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data = await response.json();

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: data.response || 'Sorry, I could not process your request.',
        role: 'assistant',
        timestamp: new Date(),
        reasoningTrace:
          typeof data.reasoning_trace === 'string' && data.reasoning_trace.trim()
            ? data.reasoning_trace.trim()
            : undefined,
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: 'Sorry, there was an error processing your request. Please make sure the backend is running.',
        role: 'assistant',
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-gradient-to-br from-slate-50 via-sky-50/30 to-blue-50/20">
      {/* Background Orbs - More stable and subtle */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-20 w-72 h-72 bg-sky-200/10 rounded-full blur-3xl animate-pulse" style={{ animationDuration: '8s', animationIterationCount: 'infinite' }}></div>
        <div className="absolute bottom-20 right-20 w-96 h-96 bg-blue-200/10 rounded-full blur-3xl animate-pulse" style={{ animationDuration: '10s', animationIterationCount: 'infinite', animationDelay: '2s' }}></div>
      </div>

      {/* Header */}
      <header className="bg-white/60 backdrop-blur-xl sticky top-0 z-10 border-b border-sky-100/50 shadow-sm">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 bg-gradient-to-r from-sky-400 to-blue-500 rounded-xl flex items-center justify-center shadow-lg shadow-sky-200/50">
                <div className="w-6 h-6 bg-white rounded-sm"></div>
              </div>
              <h1 className="text-2xl font-playfair font-bold bg-gradient-to-r from-sky-600 to-blue-700 bg-clip-text text-transparent">AI Assistant</h1>
            </div>
            <div className="text-sm text-sky-600/70">
              AI-Powered Assistant
            </div>
          </div>
        </div>
      </header>

      {/* Chat Messages */}
      <main className="flex-1 max-w-4xl w-full mx-auto px-6 py-8 relative z-10">
        <div className="space-y-6">
          {messages.length === 0 ? (
            <div className="text-center py-20">
              <div className="w-20 h-20 bg-gradient-to-r from-sky-400 to-blue-500 rounded-2xl flex items-center justify-center mx-auto mb-6 shadow-xl shadow-sky-200/50">
                <div className="w-12 h-12 bg-white rounded-lg"></div>
              </div>
              <h2 className="text-3xl font-playfair font-bold bg-gradient-to-r from-sky-600 to-blue-700 bg-clip-text text-transparent mb-4">
                Welcome
              </h2>
              <p className="text-sky-600/70 text-lg max-w-md mx-auto">
                Ask me anything! Upload a PDF or image with the paperclip to ask questions about them.
              </p>
            </div>
          ) : (
            messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`flex items-start space-x-3 max-w-2xl ${
                    message.role === 'user' ? 'flex-row-reverse space-x-reverse' : ''
                  }`}
                >
                  <div
                    className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 shadow-md ${
                      message.role === 'user'
                        ? 'bg-gradient-to-r from-sky-400 to-blue-500'
                        : 'bg-gradient-to-r from-sky-300 to-blue-400'
                    }`}
                  >
                    {message.role === 'user' ? (
                      <User className="w-4 h-4 text-white" />
                    ) : (
                      <div className="w-4 h-4 bg-white rounded-sm"></div>
                    )}
                  </div>
                  <div
                    className={`bg-white/80 backdrop-blur-sm rounded-2xl p-5 shadow-lg shadow-sky-100/50 border border-sky-100/50 transition-all duration-300 hover:shadow-xl hover:shadow-sky-100/70 ${
                      message.role === 'user' ? 'bg-gradient-to-r from-sky-50 to-blue-50' : ''
                    }`}
                  >
                    {message.image && (
                      <img 
                        src={message.image} 
                        alt="Uploaded image" 
                        className="max-w-full h-auto rounded-lg mb-3 shadow-md"
                      />
                    )}
                    <div className="prose prose-sm max-w-none prose-sky prose-headings:text-sky-700 prose-p:text-slate-700 prose-li:text-slate-700 prose-code:text-sky-600 prose-pre:bg-sky-50 prose-pre:border-sky-200">
                      <ReactMarkdown 
                        remarkPlugins={[remarkGfm]}
                        rehypePlugins={[rehypeHighlight]}
                      >
                        {message.content}
                      </ReactMarkdown>
                    </div>
                    {message.role === 'assistant' && message.reasoningTrace && (
                      <details className="mt-4 group border-t border-sky-100/50 pt-3">
                        <summary className="cursor-pointer list-none flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.15em] text-sky-500/60 hover:text-sky-500/80 transition-colors select-none [&::-webkit-details-marker]:hidden">
                          <span>Thought process</span>
                          <span className="ml-auto text-[9px] font-normal normal-case tracking-normal text-sky-400/50 tabular-nums">
                            <span className="group-open:hidden">Show</span>
                            <span className="hidden group-open:inline">Hide</span>
                          </span>
                        </summary>
                        <div className="mt-3 pl-3 border-l border-sky-200/50 max-h-48 overflow-y-auto rounded-r-md">
                          <div className="text-xs leading-relaxed text-sky-600/60 font-mono whitespace-pre-wrap">
                            {message.reasoningTrace}
                          </div>
                        </div>
                      </details>
                    )}
                    <p className="text-xs text-sky-500/50 mt-3">
                      {message.timestamp.toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              </div>
            ))
          )}
          
          {(isLoading || isUploadingPdf || isUploadingImage) && (
            <div className="flex justify-start">
              <div className="flex items-start gap-3 max-w-2xl w-full">
                <div className="relative w-9 h-9 rounded-xl flex-shrink-0">
                  <div className="absolute inset-0 rounded-xl loading-orbit animate-gradient-flow opacity-60" />
                  <div className="relative w-full h-full rounded-xl bg-gradient-to-br from-sky-300 to-blue-400 flex items-center justify-center shadow-lg shadow-sky-200/50">
                    {isUploadingPdf || isUploadingImage ? (
                      <Loader2 className="w-4 h-4 text-white animate-spin" />
                    ) : (
                      <div className="w-4 h-4 bg-white rounded-sm"></div>
                    )}
                  </div>
                </div>
                <div className="relative flex-1 min-w-0 overflow-hidden rounded-2xl">
                  <div className="absolute inset-0 loading-orbit animate-gradient-flow rounded-2xl opacity-70" />
                  <div className="relative m-[1px] rounded-[19px] bg-white/90 backdrop-blur-xl px-5 py-4 border border-sky-100/50 shadow-xl shadow-sky-100/30">
                    <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-[19px]">
                      <div className="absolute inset-y-0 w-1/2 bg-gradient-to-r from-transparent via-sky-100/30 to-transparent animate-shimmer-sweep" />
                    </div>
                    <div className="relative flex items-center gap-2 mb-2.5">
                      <span className="text-[10px] font-semibold uppercase tracking-[0.2em] text-sky-500/60 animate-thinking-pulse">
                        {isUploadingPdf ? 'Processing PDF' : isUploadingImage ? 'Processing Image' : 'Thinking'}
                      </span>
                      <span className="flex gap-1">
                        <span
                          className="w-1.5 h-1.5 rounded-full bg-sky-400/80 animate-dot-bounce"
                          style={{ animationDelay: '0ms' }}
                        />
                        <span
                          className="w-1.5 h-1.5 rounded-full bg-sky-400/80 animate-dot-bounce"
                          style={{ animationDelay: '160ms' }}
                        />
                        <span
                          className="w-1.5 h-1.5 rounded-full bg-sky-400/80 animate-dot-bounce"
                          style={{ animationDelay: '320ms' }}
                        />
                      </span>
                    </div>
                    <p className="relative text-sm text-slate-600/80 leading-relaxed min-h-[1.25rem] transition-opacity duration-500">
                      {loadingPhase || (isUploadingPdf ? PDF_LOADING_PHASES[0] : isUploadingImage ? IMAGE_LOADING_PHASES[0] : CHAT_LOADING_PHASES[0])}
                    </p>
                    <p className="relative mt-2 text-[10px] text-sky-400/50 font-mono">
                      {isUploadingPdf
                        ? 'Secure upload · local indexing'
                        : isUploadingImage
                        ? 'Analyzing image content'
                        : 'Agent reasoning will appear when ready'}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
        <div ref={messagesEndRef} />
      </main>

      {/* Input Form */}
      <footer className="bg-white/70 backdrop-blur-xl border-t border-sky-100/50 relative z-10">
        <div className="max-w-4xl mx-auto px-6 py-6">
          <form onSubmit={handleSubmit} className="flex items-center space-x-4">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={handlePdfPick}
            />
            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleImagePick}
            />
            <div className="relative" ref={attachmentMenuRef}>
              <button
                type="button"
                onClick={() => setShowAttachmentMenu(!showAttachmentMenu)}
                disabled={isLoading || isUploadingPdf || isUploadingImage || hasUploadedFile}
                title={hasUploadedFile ? "File already uploaded" : "Attach file"}
                className="flex-shrink-0 w-11 h-11 bg-white/80 backdrop-blur-sm rounded-xl flex items-center justify-center text-slate-600 hover:bg-sky-50 hover:text-sky-600 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed border border-sky-100/50 shadow-sm hover:shadow-md"
              >
                {isUploadingPdf || isUploadingImage ? (
                  <Loader2 className="w-5 h-5 text-sky-500 animate-spin" />
                ) : (
                  <Paperclip className="w-5 h-5" />
                )}
              </button>
              
              {showAttachmentMenu && (
                <div className="absolute bottom-full left-0 mb-2 w-48 bg-white/95 backdrop-blur-xl rounded-xl shadow-xl border border-sky-100/50 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => {
                      fileInputRef.current?.click();
                      setShowAttachmentMenu(false);
                    }}
                    className="w-full px-4 py-3 flex items-center space-x-3 hover:bg-sky-50 transition-colors text-left"
                  >
                    <FileText className="w-4 h-4 text-sky-600" />
                    <span className="text-sm text-slate-700">Upload PDF</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      imageInputRef.current?.click();
                      setShowAttachmentMenu(false);
                    }}
                    className="w-full px-4 py-3 flex items-center space-x-3 hover:bg-sky-50 transition-colors text-left border-t border-sky-100/50"
                  >
                    <Image className="w-4 h-4 text-sky-600" />
                    <span className="text-sm text-slate-700">Upload Image</span>
                  </button>
                </div>
              )}
            </div>
            <div className="flex-1 relative">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={isUploadingPdf ? "Indexing PDF, please wait..." : isUploadingImage ? "Processing Image..." : isLoading ? "Waiting for response..." : "Type your message..."}
                className="w-full bg-white/80 backdrop-blur-sm px-4 py-3 pr-12 rounded-xl text-slate-700 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-400/50 focus:border-sky-400 transition-all border border-sky-100/50 shadow-sm disabled:bg-slate-100 disabled:text-slate-500"
                disabled={isLoading || isUploadingPdf || isUploadingImage}
              />
              <button
                type="submit"
                disabled={!input.trim() || isLoading || isUploadingPdf || isUploadingImage}
                className="absolute right-2 top-1/2 transform -translate-y-1/2 w-8 h-8 bg-gradient-to-r from-sky-400 to-blue-500 rounded-lg flex items-center justify-center text-white hover:from-sky-500 hover:to-blue-600 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm hover:shadow-md"
              >
                {isLoading || isUploadingPdf || isUploadingImage ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            </div>
          </form>
        </div>
      </footer>
    </div>
  );
};

export default ChatInterface;
