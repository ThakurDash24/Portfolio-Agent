"use client";

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { cn } from '../../lib/utils';
import {
    SendIcon,
    XIcon,
    LoaderIcon,
    ChevronDown,
    ChevronUp,
    User,
    Sparkles,
    Trash2,
    Plus,
    Menu,
    History,
    Search,
    FileText,
    ImageIcon,
    MonitorIcon,
    PenTool,
    LogOut
} from "lucide-react";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { motion, AnimatePresence } from "framer-motion";
import GradientMenu from './gradient-menu';
import { useNavigate } from 'react-router-dom';
import { getAccessToken, supabase } from '../../lib/supabaseClient';

interface Message {
    id: string;
    content: string;
    role: 'user' | 'assistant';
    timestamp: Date;
    imagePreview?: string;
    pdfName?: string;
    reasoningTrace?: string;
}


interface UseAutoResizeTextareaProps {
    minHeight: number;
    maxHeight?: number;
}

function useAutoResizeTextarea({
    minHeight,
    maxHeight,
}: UseAutoResizeTextareaProps) {
    const textareaRef = React.useRef<HTMLTextAreaElement>(null);

    const adjustHeight = React.useCallback(() => {
        const textarea = textareaRef.current;
        if (!textarea) return;

        textarea.style.height = `${minHeight}px`;
        textarea.style.overflow = 'hidden';

        const newHeight = Math.max(
            minHeight,
            Math.min(
                maxHeight ?? Number.POSITIVE_INFINITY,
                textarea.scrollHeight
            )
        );

        textarea.style.height = `${newHeight}px`;
    }, [minHeight, maxHeight]);

    React.useEffect(() => {
        const handleResize = () => adjustHeight();
        window.addEventListener('resize', handleResize);
        return () => {
            window.removeEventListener('resize', handleResize);
        };
    }, [adjustHeight]);

    return { textareaRef, adjustHeight };
}

interface CommandSuggestion {
    icon: React.ReactNode;
    label: string;
    description: string;
    prefix: string;
}

interface TextareaProps
    extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
    containerClassName?: string;
    showRing?: boolean;
}

const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
    ({ className, containerClassName, showRing = true, ...props }, ref) => {
        const [isFocused, setIsFocused] = React.useState(false);

        return (
            <div className={cn(
                "relative",
                containerClassName
            )}>
                <textarea
                    className={cn(
                        "flex w-full px-3 py-2 text-sm bg-transparent border-none",
                        "transition-all duration-200 ease-in-out",
                        "placeholder:text-white/20",
                        "disabled:cursor-not-allowed disabled:opacity-50",
                        "focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0",
                        "focus:outline-none focus:ring-0 border-0 outline-none shadow-none",
                        className
                    )}
                    style={{ boxShadow: 'none', border: 'none', outline: 'none' }}
                    ref={ref}
                    onFocus={() => setIsFocused(true)}
                    onBlur={() => setIsFocused(false)}
                    {...props}
                />

                {showRing && isFocused && (
                    <motion.span
                        className="absolute inset-0 rounded-md pointer-events-none ring-2 ring-offset-0 ring-violet-500/30"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.2 }}
                    />
                )}

                {props.onChange && (
                    <div
                        className="absolute bottom-2 right-2 opacity-0 w-2 h-2 bg-violet-500 rounded-full"
                        style={{
                            animation: 'none',
                        }}
                        id="textarea-ripple"
                    />
                )}
            </div>
        )
    }
)
Textarea.displayName = "Textarea"

export function AnimatedAIChat() {
    const apiBaseUrl = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";
    const [messages, setMessages] = useState<Message[]>([]);
    const [value, setValue] = useState("");
    const [attachments, setAttachments] = useState<string[]>([]);
    const [isTyping, setIsTyping] = useState(false);
    const [activeSuggestion, setActiveSuggestion] = useState<number>(-1);
    const [showCommandPalette, setShowCommandPalette] = useState(false);
    const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
    const [inputFocused, setInputFocused] = useState(false);
    const [statusLabel, setStatusLabel] = useState<string | null>(null);
    const imageInputRef = useRef<HTMLInputElement>(null);
    const pdfInputRef = useRef<HTMLInputElement>(null);
    const commandPaletteRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const { adjustHeight } = useAutoResizeTextarea({ minHeight: 60, maxHeight: 200 });
    const [isHeaderScrolled, setIsHeaderScrolled] = useState(false);
    const [currentHasPdf, setCurrentHasPdf] = useState(false);
    const [currentHasPhoto, setCurrentHasPhoto] = useState(false);
    const [userEmail, setUserEmail] = useState<string | null>(null);
    const navigate = useNavigate();

    // 🔐 Auth guard: redirect to login if no active Supabase session
    useEffect(() => {
        supabase.auth.getSession().then(({ data }: { data: { session: any } }) => {
            if (!data.session) {
                navigate('/login', { replace: true });
            } else {
                setUserEmail(data.session.user?.email || null);
            }
        });
    }, [navigate]);

    /** Returns headers with Bearer token for authenticated API calls. Throws if no session. */
    const authHeaders = async (): Promise<Record<string, string>> => {
        const token = await getAccessToken();
        if (!token) {
            navigate('/login', { replace: true });
            throw new Error('No auth token — redirecting to login');
        }
        return {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        };
    };

    const commandSuggestions = useMemo<CommandSuggestion[]>(() => [
        {
            icon: <Search className="w-4 h-4" />,
            label: "Browser Search",
            description: "Search live via visible Chrome",
            prefix: "/browser"
        },
        {
            icon: <ImageIcon className="w-4 h-4" />,
            label: "Clone UI",
            description: "Generate a UI from a screenshot",
            prefix: "/clone"
        },
        {
            icon: <MonitorIcon className="w-4 h-4" />,
            label: "Create Page",
            description: "Generate a new web page",
            prefix: "/page"
        },
    ], []);

    useEffect(() => {
        if (value.startsWith('/') && !value.includes(' ')) {
            setShowCommandPalette(true);

            const matchingSuggestionIndex = commandSuggestions.findIndex(
                (cmd) => cmd.prefix.startsWith(value)
            );

            if (matchingSuggestionIndex >= 0) {
                setActiveSuggestion(matchingSuggestionIndex);
            } else {
                setActiveSuggestion(-1);
            }
        } else {
            setShowCommandPalette(false);
        }
    }, [value, commandSuggestions]);

    const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
    const scrollContainerRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
        if (scrollContainerRef.current) {
            scrollContainerRef.current.scrollTo({
                top: scrollContainerRef.current.scrollHeight,
                behavior
            });
        }
    }, []);

    const handleScroll = () => {
        if (!scrollContainerRef.current) return;
        const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
        
        // 1. Existing Auto-scroll logic
        const isAtBottom = scrollHeight - scrollTop - clientHeight < 100;
        setShouldAutoScroll(isAtBottom);

        // 2. Premium Header scroll detection (Threshold 50px)
        setIsHeaderScrolled(scrollTop > 50);
    };

    useEffect(() => {
        if (shouldAutoScroll) {
            scrollToBottom();
        }
    }, [messages, isTyping, shouldAutoScroll, scrollToBottom]);

    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => {
            setMousePosition({ x: e.clientX, y: e.clientY });
        };

        window.addEventListener('mousemove', handleMouseMove);
        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
        };
    }, []);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            const target = event.target as Node;
            const commandButton = document.querySelector('[data-command-button]');

            if (commandPaletteRef.current &&
                !commandPaletteRef.current.contains(target) &&
                !commandButton?.contains(target)) {
                setShowCommandPalette(false);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, []);

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (showCommandPalette) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActiveSuggestion(prev =>
                    prev < commandSuggestions.length - 1 ? prev + 1 : 0
                );
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActiveSuggestion(prev =>
                    prev > 0 ? prev - 1 : commandSuggestions.length - 1
                );
            } else if (e.key === 'Tab' || e.key === 'Enter') {
                e.preventDefault();
                if (activeSuggestion >= 0) {
                    const selectedCommand = commandSuggestions[activeSuggestion];
                    setValue(selectedCommand.prefix + ' ');
                    setShowCommandPalette(false);
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                setShowCommandPalette(false);
            }
        } else if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (value.trim()) {
                handleSendMessage();
            }
        }
    };

    const handleSendMessage = async () => {
        if (!value.trim() && attachments.length === 0) return;

        const userMessage: Message = {
            id: Date.now().toString(),
            content: value,
            role: 'user',
            timestamp: new Date(),
            imagePreview: attachments.find(a => a.startsWith('blob:')) || undefined,
            pdfName: attachments.find(a => a.endsWith('.pdf')) || undefined,
        };

        setMessages(prev => [...prev, userMessage]);
        setValue("");
        setAttachments([]);
        setIsTyping(true);
        setStatusLabel("Laven is thinking");

        try {
            let activeThreadId = currentThreadId;

            // If no thread exists, create one BEFORE sending the message
            if (!activeThreadId) {
                const headers = await authHeaders();
                const response = await fetch(`${apiBaseUrl}/threads/new`, {
                    method: "POST",
                    headers,
                });
                if (!response.ok) throw new Error("Failed to create thread");
                const threadData = await response.json();
                activeThreadId = threadData.thread_id;
                setCurrentThreadId(activeThreadId);
            }

            let imagesBase64: string[] = [];
            const imageAttachments = attachments.filter(a => a.startsWith('blob:'));
            for (const url of imageAttachments) {
                const res = await fetch(url);
                const blob = await res.blob();
                const reader = new FileReader();
                const dataUrl = await new Promise<string>((resolve) => {
                    reader.onloadend = () => resolve(reader.result as string);
                    reader.readAsDataURL(blob);
                });
                imagesBase64.push(dataUrl);
            }

            const chatHeaders = await authHeaders();
            const response = await fetch(`${apiBaseUrl}/chat`, {
                method: "POST",
                headers: chatHeaders,
                body: JSON.stringify({
                    message: userMessage.content,
                    thread_id: activeThreadId,
                    images: imagesBase64.length > 0 ? imagesBase64 : undefined
                }),
            });

            if (!response.ok) throw new Error("Failed to get response");

            const data = await response.json();

            // Sync session restrictions
            if (data.has_pdf !== undefined) setCurrentHasPdf(data.has_pdf);
            if (data.has_image !== undefined) setCurrentHasPhoto(data.has_image);
            
            // Fetch threads to update the sidebar titles
            fetchThreads();

            // Update 'Saved' status if agent triggered save_session_tool
            if (data.saved) {
                setIsSaved(true);
            }

            // Prepare assistant message for streaming
            const assistantMessage: Message = {
                id: (Date.now() + 1).toString(),
                content: "", // Start empty for streaming
                role: 'assistant',
                timestamp: new Date(),
                reasoningTrace: data.reasoning_trace,
            };

            setMessages(prev => [...prev, assistantMessage]);

            // Simulation of streaming effect
            const fullResponse = data.response;
            let currentText = "";
            const words = fullResponse.split(' ');

            for (let i = 0; i < words.length; i++) {
                currentText += (i === 0 ? "" : " ") + words[i];
                // eslint-disable-next-line no-loop-func
                setMessages(prev => {
                    const newMessages = [...prev];
                    const lastIdx = newMessages.length - 1;
                    if (newMessages[lastIdx].id === assistantMessage.id) {
                        newMessages[lastIdx] = { ...newMessages[lastIdx], content: currentText };
                    }
                    return newMessages;
                });
                // Small delay to simulate typing
                await new Promise(resolve => setTimeout(resolve, 30 + Math.random() * 20));
            }
        } catch (error) {
            console.error("Chat error:", error);
            const errorMessage: Message = {
                id: (Date.now() + 1).toString(),
                content: "Sorry, I encountered an error. Please try again.",
                role: 'assistant',
                timestamp: new Date(),
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsTyping(false);
            setStatusLabel(null);
            adjustHeight();
        }
    };

    const handleImageUpload = () => {
        imageInputRef.current?.click();
    };

    const handlePdfUpload = () => {
        pdfInputRef.current?.click();
    };

    const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>, type: 'image' | 'pdf') => {
        const file = e.target.files?.[0];
        if (!file) return;

        // Preview
        if (type === 'image') {
            const url = URL.createObjectURL(file);
            setAttachments(prev => [...prev, url]);

            // Upload to backend
            const formData = new FormData();
            formData.append('file', file);
            try {
                setStatusLabel("Uploading image...");
                setIsTyping(true);
                const imageToken = await getAccessToken();
                const res = await fetch(`${apiBaseUrl}/upload/image${currentThreadId ? `?thread_id=${currentThreadId}` : ''}`, {
                    method: "POST",
                    headers: imageToken ? { 'Authorization': `Bearer ${imageToken}` } : {},
                    body: formData,
                });
                const data = await res.json();
                if (data.has_image) setCurrentHasPhoto(true);
            } catch (err) {
                console.error("Image upload failed", err);
            } finally {
                setIsTyping(false);
                setStatusLabel(null);
            }
        } else {
            setAttachments(prev => [...prev, file.name]);

            // Upload to backend
            let activeThreadId = currentThreadId;
            if (!activeThreadId) {
                try {
                    const headers = await authHeaders();
                    const response = await fetch(`${apiBaseUrl}/threads/new`, {
                        method: "POST",
                        headers,
                    });
                    const threadData = await response.json();
                    activeThreadId = threadData.thread_id;
                    setCurrentThreadId(activeThreadId);
                } catch (err) {
                    console.error("Failed to create thread for PDF upload", err);
                    return;
                }
            }

            const formData = new FormData();
            formData.append('file', file);
            try {
                setStatusLabel("Indexing PDF for this session...");
                setIsTyping(true);
                const pdfToken = await getAccessToken();
                const res = await fetch(`${apiBaseUrl}/upload/pdf?thread_id=${activeThreadId}`, {
                    method: "POST",
                    headers: pdfToken ? { 'Authorization': `Bearer ${pdfToken}` } : {},
                    body: formData,
                });
                const data = await res.json();
                if (data.has_pdf) setCurrentHasPdf(true);
            } catch (err) {
                console.error("PDF upload failed", err);
            } finally {
                setIsTyping(false);
                setStatusLabel(null);
            }
        }
    };



    const handleWebSearch = () => {
        setValue('/browser ');
        textareaRef.current?.focus();
    };

    const removeAttachment = (index: number) => {
        setAttachments(prev => prev.filter((_, i) => i !== index));
    };

    const selectCommandSuggestion = (index: number) => {
        const selectedCommand = commandSuggestions[index];
        setValue(selectedCommand.prefix + ' ');
        setShowCommandPalette(false);
    };

    const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
    const [threads, setThreads] = useState<{ id: string, title: string }[]>([]);
    const [showSidebar, setShowSidebar] = useState(false);
    const [isSaved, setIsSaved] = useState(false);
    const [editingThreadId, setEditingThreadId] = useState<string | null>(null);
    const [editingTitle, setEditingTitle] = useState("");

    const fetchThreads = async () => {
        try {
            const token = await getAccessToken();
            if (!token) return; // Not logged in yet, skip silently
            const headers = {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
            };
            const response = await fetch(`${apiBaseUrl}/threads`, { headers });
            if (!response.ok) {
                console.warn('fetchThreads HTTP error:', response.status);
                setThreads([]);
                return;
            }
            const data = await response.json();
            if (Array.isArray(data)) {
                setThreads(data);
            } else {
                console.warn("Expected array for threads, got:", data);
                setThreads([]);
            }
        } catch (e) {
            console.error("Failed to fetch threads", e);
        }
    };

    useEffect(() => {
        fetchThreads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleNewChat = () => {
        setMessages([]);
        setCurrentThreadId(null);
        setShowSidebar(false);
        setValue("");
        setAttachments([]);
        setIsSaved(false);
        setCurrentHasPdf(false);
        setCurrentHasPhoto(false);
    };

    const handleSaveSession = async () => {
        if (!currentThreadId) return;
        try {
            const headers = await authHeaders();
            const response = await fetch(`${apiBaseUrl}/save_thread/${currentThreadId}`, {
                method: "POST",
                headers,
            });
            if (response.ok) {
                setIsSaved(true);
                fetchThreads();
                setTimeout(() => setIsSaved(false), 3000);
            }
        } catch (e) {
            console.error("Failed to save thread", e);
        }
    };

    const loadThread = async (id: string) => {
        try {
            const headers = await authHeaders();
            const response = await fetch(`${apiBaseUrl}/thread/${id}`, { headers });
            const data = await response.json();
            // Map formatted messages back to Message objects
            const loadedMessages: Message[] = data.messages.map((m: any) => {
                let rawContent = m.content || m.text || "";
                if (Array.isArray(rawContent)) {
                    rawContent = rawContent.filter((item: any) => item.type === 'text').map((item: any) => item.text).join('\n');
                }
                return {
                    id: m.id || Math.random().toString(),
                    content: typeof rawContent === 'string' ? rawContent : JSON.stringify(rawContent),
                    role: m.role || 'assistant',
                    timestamp: new Date()
                };
            });
            setMessages(loadedMessages);
            setCurrentThreadId(id);
            setIsSaved(data.saved); // Correctly reflect saved status from backend
            setCurrentHasPdf(data.has_pdf || false);
            setCurrentHasPhoto(data.has_image || false);
            textareaRef.current?.focus();
            setIsSaved(data.saved || false);
            setShowSidebar(false);
        } catch (e) {
            console.error("Failed to load thread", e);
        }
    };

    const deleteThreadFromHistory = async (id: string, e: React.MouseEvent) => {
        e.stopPropagation();
        try {
            const headers = await authHeaders();
            await fetch(`${apiBaseUrl}/threads/${id}`, { method: 'DELETE', headers });
            if (currentThreadId === id) handleNewChat();
            fetchThreads();
        } catch (e) {
            console.error("Failed to delete thread", e);
        }
    };

    const handleEditTitle = (e: React.MouseEvent, id: string, currentTitle: string) => {
        e.stopPropagation();
        setEditingThreadId(id);
        setEditingTitle(currentTitle);
    };

    const saveEditedTitle = async (id: string) => {
        if (!editingTitle.trim()) {
            setEditingThreadId(null);
            return;
        }
        try {
            const headers = await authHeaders();
            await fetch(`${apiBaseUrl}/threads/${id}/title`, {
                method: "PUT",
                headers,
                body: JSON.stringify({ title: editingTitle.trim() }),
            });
            fetchThreads();
        } catch (e) {
            console.error("Failed to update thread title", e);
        } finally {
            setEditingThreadId(null);
        }
    };

    const handleSignOut = async () => {
        await supabase.auth.signOut();
        navigate('/login');
    };

    const isChatMode = messages.length > 0;

    return (
        <div className="h-screen flex flex-col w-full bg-transparent text-white relative overflow-hidden font-sans">
            <header className={cn(
                "fixed top-0 left-0 right-0 z-50 transition-all duration-500 ease-in-out px-4 md:px-6 w-full flex justify-center",
                isHeaderScrolled 
                    ? "py-3 bg-black/40 backdrop-blur-xl border-b border-white/5 shadow-2xl shadow-black/50" 
                    : "py-6 md:py-8 bg-transparent backdrop-blur-none border-b-0"
            )}>
                <nav className="w-full flex items-center justify-between relative">
                    
                    {/* Left: Navigation Controls */}
                    <div className="flex items-center gap-3 z-10">
                        <button 
                            onClick={() => setShowSidebar(!showSidebar)}
                            className="p-2.5 rounded-xl bg-white/5 border border-white/10 hover:bg-violet-500/20 hover:border-violet-500/50 transition-all duration-300 text-white/50 hover:text-white group pointer-events-auto"
                            title="History"
                        >
                            <Menu className="w-5 h-5 group-hover:scale-110 transition-transform" />
                        </button>
                        <button 
                            onClick={handleNewChat}
                            className="p-2.5 rounded-xl bg-white/5 border border-white/10 hover:bg-violet-500/20 hover:border-violet-500/50 transition-all duration-300 text-white/50 hover:text-white group pointer-events-auto"
                            title="New Chat"
                        >
                            <Plus className="w-5 h-5 group-hover:scale-110 transition-transform" />
                        </button>
                    </div>

                    {/* Highly Precise Center: Branding Logo - Hidden on mobile to avoid overlap */}
                    <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none hidden md:block">
                        <motion.div 
                            initial={{ opacity: 0, y: -10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.8, ease: "easeOut" }}
                            className="relative flex items-center"
                        >
                            <div className="relative px-4 py-1.5 rounded-2xl pointer-events-auto cursor-pointer">
                                <span className={cn(
                                    "relative z-10 text-3xl font-playfair font-bold tracking-tighter transition-all duration-500",
                                    isHeaderScrolled ? "scale-90 opacity-90" : "scale-100 opacity-100"
                                )}>
                                    Laven<span className="text-violet-400">.</span>
                                </span>
                            </div>
                        </motion.div>
                    </div>

                    {/* Right: Save Session Actions & Account */}
                    <div className="flex justify-end items-center gap-4 z-10">
                        {currentThreadId && (
                            <motion.button
                                initial={{ opacity: 0, scale: 0.9 }}
                                animate={{ opacity: 1, scale: 1 }}
                                onClick={handleSaveSession}
                                className={cn(
                                    "px-5 py-2.5 rounded-xl border text-[10px] font-bold uppercase tracking-[0.2em] transition-all duration-500 pointer-events-auto",
                                    isSaved 
                                        ? "bg-green-500/20 border-green-500/50 text-green-400 shadow-[0_0_20px_rgba(34,197,94,0.15)]" 
                                        : "bg-white/5 border-white/10 text-white/40 hover:border-violet-500/50 hover:text-white hover:bg-violet-500/10"
                                )}
                            >
                                {isSaved ? "Saved ✓" : "Save Chat"}
                            </motion.button>
                        )}
                        
                        {/* Persistent Account Section - Collaborative View on Mobile */}
                        <div className="flex items-center gap-2 sm:gap-3 bg-white/5 border border-white/10 px-2 sm:px-3 py-1.5 rounded-xl backdrop-blur-md pointer-events-auto shadow-lg">
                            <div className="hidden sm:flex flex-col items-end pr-3 border-r border-white/10">
                                <span className="text-[9px] text-white/40 uppercase tracking-widest font-bold">Account</span>
                                <span className="text-xs font-medium text-white/80">{userEmail || 'User'}</span>
                            </div>
                            <button 
                                onClick={handleSignOut}
                                className="p-2 rounded-lg hover:bg-red-500/20 transition-all duration-300 text-white/40 hover:text-red-400 group focus:outline-none flex items-center gap-2"
                                title="Sign Out"
                            >
                                <span className="text-[10px] sm:hidden font-bold uppercase tracking-widest opacity-60">Exit</span>
                                <LogOut className="w-4 h-4 group-hover:scale-110 transition-transform" />
                            </button>
                        </div>
                    </div>
                </nav>
            </header>

            {/* Thread History Sidebar */}
            <AnimatePresence>
                {showSidebar && (
                    <motion.div
                        initial={{ opacity: 0, x: -50 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -50 }}
                        className="fixed left-4 sm:left-8 top-24 sm:top-32 bottom-4 sm:bottom-8 w-[calc(100%-2rem)] sm:w-64 bg-black/60 backdrop-blur-3xl border border-white/10 rounded-2xl z-40 overflow-hidden flex flex-col shadow-2xl"
                    >
                        <div className="p-4 border-b border-white/5 flex items-center justify-between">
                            <span className="text-[10px] uppercase font-bold tracking-widest text-white/40 flex items-center gap-2">
                                <History className="w-3 h-3" /> Recent Chats
                            </span>
                        </div>
                        <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
                            {Array.isArray(threads) && threads.length === 0 ? (
                                <div className="text-[10px] text-white/20 text-center py-8">No history yet</div>
                            ) : (
                                Array.isArray(threads) && threads.map(thread => (
                                    <div
                                        key={thread.id}
                                        onClick={() => {
                                            if (editingThreadId !== thread.id) {
                                                loadThread(thread.id);
                                            }
                                        }}
                                        className={cn(
                                            "group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all duration-300",
                                            currentThreadId === thread.id
                                                ? "bg-violet-500/20 border border-violet-500/30 text-white"
                                                : "text-white/40 hover:bg-white/5 hover:text-white/80"
                                        )}
                                    >
                                        {editingThreadId === thread.id ? (
                                            <input
                                                type="text"
                                                autoFocus
                                                value={editingTitle}
                                                onChange={(e) => setEditingTitle(e.target.value)}
                                                onBlur={() => saveEditedTitle(thread.id)}
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Enter') saveEditedTitle(thread.id);
                                                    if (e.key === 'Escape') setEditingThreadId(null);
                                                }}
                                                className="flex-1 bg-black/40 border border-white/20 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-violet-500 mr-2 min-w-0"
                                                onClick={(e) => e.stopPropagation()}
                                            />
                                        ) : (
                                            <span className="text-xs truncate flex-1 pr-2">{thread.title}</span>
                                        )}
                                        {editingThreadId !== thread.id && (
                                            <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-opacity">
                                                <button
                                                    onClick={(e) => handleEditTitle(e, thread.id, thread.title)}
                                                    className="p-1 text-white/40 hover:text-white transition-colors"
                                                >
                                                    <PenTool className="w-3 h-3" />
                                                </button>
                                                <button
                                                    onClick={(e) => deleteThreadFromHistory(thread.id, e)}
                                                    className="p-1 text-white/40 hover:text-red-400 transition-colors"
                                                >
                                                    <Trash2 className="w-3 h-3" />
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                ))
                            )}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Background Beams are handled by the parent wrapper in App.tsx */}

            {/* Main Layout Container */}
            <div className={cn(
                "flex-1 min-h-0 flex flex-col w-full relative z-10",
                !isChatMode ? "justify-center items-center" : ""
            )}>
                {/* Chat Container (Scrollable) */}
                <div
                    ref={scrollContainerRef}
                    onScroll={handleScroll}
                    className={cn(
                        "w-full custom-scrollbar transition-all duration-500",
                        isChatMode ? "flex-1 overflow-y-auto px-4 pt-24 pb-[30vh] relative z-1" : "h-0 overflow-hidden"
                    )}
                >
                    <div className="max-w-5xl mx-auto flex flex-col gap-10">
                        <AnimatePresence>
                            {isChatMode && messages.map((message) => (
                                <MessageBubble key={message.id} message={message} />
                            ))}
                        </AnimatePresence>

                        {isTyping && statusLabel && (
                            <motion.div
                                initial={{ opacity: 0, y: 10, filter: "blur(4px)" }}
                                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                                className="flex items-center gap-2 mb-4 ml-12"
                            >
                                <TypingDots />
                                <span className="text-[10px] uppercase font-bold tracking-[0.2em] text-white/40 italic">
                                    {statusLabel}
                                </span>
                            </motion.div>
                        )}
                    </div>
                </div>

                {/* Landing State Content */}
                {!isChatMode && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="flex flex-col items-center mb-12"
                    >
                        <h1 className="text-3xl sm:text-5xl font-medium tracking-tight bg-clip-text text-transparent bg-[linear-gradient(110deg,#ffffffad,45%,#ffffff,55%,#ffffffad)] bg-[length:200%_100%] animate-text-shimmer mb-4 text-center px-4">
                            How can I help today?
                        </h1>
                        <p className="text-lg sm:text-xl text-white/50 font-light italic">
                            Hey, Laven is here ;)
                        </p>
                    </motion.div>
                )}

                <div className={cn(
                    "w-full px-4 transition-all duration-700 z-10 relative",
                    isChatMode ? "fixed bottom-0 left-0 right-0 py-6 sm:py-10 bg-gradient-to-t from-black via-black/95 to-transparent" : "max-w-5xl"
                )}>
                    <div className="max-w-5xl mx-auto flex flex-col gap-6">
                        <motion.div
                            layout
                            className={cn(
                                "relative backdrop-blur-3xl rounded-3xl border transition-all duration-500",
                                (value.length > 0 || inputFocused)
                                    ? "bg-white/[0.12] border-white/30 shadow-[0_0_50px_rgba(255,255,255,0.15)]"
                                    : "bg-white/[0.08] border-white/10 shadow-2xl"
                            )}
                        >
                            <AnimatePresence>
                                {showCommandPalette && (
                                    <motion.div
                                        ref={commandPaletteRef}
                                        className="absolute left-4 right-4 bottom-full mb-3 backdrop-blur-3xl bg-black/95 rounded-2xl z-50 shadow-2xl border border-white/10 overflow-hidden"
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: 10 }}
                                    >
                                        <div className="py-2">
                                            {/* Command suggestions - updated to reflect browser focus */}
                                            {commandSuggestions.map((suggestion, index) => (
                                                <div
                                                    key={suggestion.prefix}
                                                    className={cn(
                                                        "flex items-center gap-4 px-5 py-4 text-xs transition-all cursor-pointer",
                                                        activeSuggestion === index
                                                            ? "bg-violet-500/20 text-white"
                                                            : "text-white/40 hover:bg-white/5 hover:text-white/70"
                                                    )}
                                                    onClick={() => selectCommandSuggestion(index)}
                                                >
                                                    <div className="p-2.5 rounded-xl bg-white/5">
                                                        {suggestion.icon}
                                                    </div>
                                                    <div className="flex flex-col">
                                                        <span className="font-semibold tracking-wide text-sm">{suggestion.label}</span>
                                                        <span className="text-[10px] opacity-40 uppercase tracking-tighter">{suggestion.description}</span>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            <div className="min-h-[42px] relative px-4 py-1 flex items-center gap-4">
                                <Textarea
                                    ref={textareaRef}
                                    value={value}
                                    disabled={isTyping}
                                    onChange={(e) => {
                                        setValue(e.target.value);
                                        adjustHeight();
                                    }}
                                    onKeyDown={handleKeyDown}
                                    onFocus={() => setInputFocused(true)}
                                    onBlur={() => setInputFocused(false)}
                                    placeholder={isTyping ? "Please wait..." : "Message Laven..."}
                                    containerClassName="w-full flex-1"
                                    className="flex-1 bg-transparent border-none focus-visible:ring-0 text-white placeholder:text-white/20 resize-none py-1.5 text-base custom-scrollbar min-h-[30px]"
                                    style={{ overflow: "hidden" }}
                                    showRing={false}
                                />
                                <motion.button
                                    type="button"
                                    onClick={handleSendMessage}
                                    whileHover={{ scale: 1.1 }}
                                    whileTap={{ scale: 0.9 }}
                                    disabled={isTyping || !value.trim()}
                                    className={cn(
                                        "p-3 rounded-2xl transition-all duration-300",
                                        value.trim()
                                            ? "bg-violet-500 text-white shadow-[0_0_30px_rgba(139,92,246,0.6)]"
                                            : "bg-white/5 text-white/20 pointer-events-none"
                                    )}
                                >
                                    {isTyping ? <LoaderIcon className="w-5 h-5 animate-spin" /> : <SendIcon className="w-5 h-5" />}
                                </motion.button>
                            </div>

                            {/* Attachments inside input */}
                            <AnimatePresence>
                                {attachments.length > 0 && (
                                    <motion.div
                                        className="px-6 pb-6 flex gap-2 flex-wrap"
                                        initial={{ opacity: 0, height: 0 }}
                                        animate={{ opacity: 1, height: "auto" }}
                                    >
                                        {attachments.map((file, index) => (
                                            <motion.div
                                                key={index}
                                                className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest bg-white/5 py-2 px-3 rounded-xl border border-white/5 text-white/70"
                                            >
                                                <span>{file}</span>
                                                <button onClick={() => removeAttachment(index)} className="hover:text-red-400">
                                                    <XIcon className="w-3 h-3" />
                                                </button>
                                            </motion.div>
                                        ))}
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </motion.div>

                        {/* Action Buttons OUTSIDE in Landing Mode, Integrated in Chat Mode */}
                        {!isChatMode ? (
                            <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                className="flex justify-center"
                            >
                                <GradientMenu
                                    onPhotoUpload={handleImageUpload}
                                    onPdfUpload={handlePdfUpload}
                                    onWebSearch={handleWebSearch}
                                    hasPhoto={currentHasPhoto}
                                    hasPdf={currentHasPdf}
                                />
                            </motion.div>
                        ) : (
                            <div className="flex gap-2 opacity-60 hover:opacity-100 transition-opacity">
                                <GradientMenu
                                    onPhotoUpload={handleImageUpload}
                                    onPdfUpload={handlePdfUpload}
                                    onWebSearch={handleWebSearch}
                                    hasPhoto={currentHasPhoto}
                                    hasPdf={currentHasPdf}
                                />
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {inputFocused && (
                <motion.div
                    className="fixed w-[60rem] h-[60rem] rounded-full pointer-events-none z-0 opacity-10 bg-gradient-to-r from-violet-500/20 via-fuchsia-500/20 to-indigo-500/20 blur-[160px]"
                    animate={{ x: mousePosition.x - 480, y: mousePosition.y - 480 }}
                    transition={{ type: "spring", damping: 30, stiffness: 200 }}
                />
            )}

            <input ref={imageInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => onFileChange(e, 'image')} />
            <input ref={pdfInputRef} type="file" accept=".pdf" className="hidden" onChange={(e) => onFileChange(e, 'pdf')} />
        </div>
    );
}

function MessageBubble({ message }: { message: Message }) {
    const isAssistant = message.role === 'assistant';
    const [showReasoning, setShowReasoning] = useState(false);

    const variants = {
        hidden: { opacity: 0, y: 20, scale: 0.98, filter: "blur(4px)" },
        visible: {
            opacity: 1,
            y: 0,
            scale: 1,
            filter: "blur(0px)",
            transition: {
                duration: 0.3,
                ease: "easeOut" as any,
                opacity: { duration: 0.2 },
                y: { type: "spring", stiffness: 300, damping: 30 }
            }
        }
    };

    return (
        <motion.div
            variants={variants}
            initial="hidden"
            animate="visible"
            className={cn(
                "flex w-full group/message",
                isAssistant ? "justify-start" : "justify-end"
            )}
        >
            <div className={cn(
                "flex max-w-[95%] sm:max-w-[85%] gap-2 sm:gap-4",
                isAssistant ? "flex-row" : "flex-row-reverse"
            )}>
                <motion.div
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ delay: 0.1 }}
                    className={cn(
                        "w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 mt-1 shadow-inner",
                        isAssistant
                            ? "bg-gradient-to-br from-violet-500/20 to-fuchsia-500/10 border border-white/10"
                            : "bg-white/5 border border-white/10"
                    )}
                >
                    {isAssistant ? <Sparkles className="w-5 h-5 text-violet-400" /> : <User className="w-5 h-5 text-white/70" />}
                </motion.div>

                <div className="flex flex-col gap-2 min-w-0">
                    <div className={cn(
                        "rounded-2xl px-5 py-3.5 text-sm relative transition-all duration-500 backdrop-blur-md font-sans",
                        isAssistant
                            ? "bg-white/[0.04] border border-white/10 text-white/90 shadow-2xl"
                            : "bg-violet-500/10 border border-violet-500/20 text-white shadow-lg"
                    )}>
                        {message.imagePreview && (
                            <motion.div
                                initial={{ opacity: 0, scale: 0.9 }}
                                animate={{ opacity: 1, scale: 1 }}
                                className="mb-3 overflow-hidden rounded-xl border border-white/10"
                            >
                                <img
                                    src={message.imagePreview}
                                    alt="Preview"
                                    className="max-w-md w-full object-cover transition-transform duration-500 hover:scale-105"
                                />
                            </motion.div>
                        )}

                        {message.pdfName && (
                            <div className="flex items-center gap-3 mb-3 p-3 rounded-xl bg-white/5 border border-white/10">
                                <div className="p-2 rounded-lg bg-red-500/20">
                                    <FileText className="w-5 h-5 text-red-400" />
                                </div>
                                <div className="flex flex-col min-w-0">
                                    <span className="text-xs font-semibold text-white/90 truncate">{message.pdfName}</span>
                                    <span className="text-[10px] text-white/40 uppercase tracking-widest">Indexed Document</span>
                                </div>
                            </div>
                        )}

                        <div className="prose prose-invert prose-sm max-w-none leading-relaxed prose-p:my-0 pb-1">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                {message.content}
                            </ReactMarkdown>
                        </div>

                        {message.reasoningTrace && (
                            <div className="mt-4 pt-4 border-t border-white/10 space-y-3">
                                <button
                                    onClick={() => setShowReasoning(!showReasoning)}
                                    className="flex items-center gap-2 group/btn"
                                >
                                    <div className={cn(
                                        "p-1 rounded-md transition-all duration-300",
                                        showReasoning ? "bg-violet-500/20 text-violet-400" : "bg-white/5 text-white/40 group-hover/btn:text-white/60"
                                    )}>
                                        {showReasoning ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                                    </div>
                                    <span className="text-[10px] uppercase font-bold tracking-[0.2em] text-white/30 group-hover/btn:text-white/50 transition-colors">
                                        System Reasoning
                                    </span>
                                </button>

                                <AnimatePresence>
                                    {showReasoning && (
                                        <motion.div
                                            initial={{ height: 0, opacity: 0, filter: "blur(8px)" }}
                                            animate={{ height: "auto", opacity: 1, filter: "blur(0px)" }}
                                            exit={{ height: 0, opacity: 0, filter: "blur(8px)" }}
                                            transition={{ type: "spring", stiffness: 100, damping: 20 }}
                                            className="overflow-hidden"
                                        >
                                            <div className="p-5 rounded-2xl bg-black/60 border border-white/10 shadow-inner overflow-hidden">
                                                <div className="space-y-3">
                                                    {message.reasoningTrace.split('\n').map((line, idx) => (
                                                        <motion.div
                                                            key={idx}
                                                            initial={{ opacity: 0, x: -10 }}
                                                            animate={{ opacity: 1, x: 0 }}
                                                            transition={{ delay: idx * 0.1 }}
                                                            className="flex gap-3 items-start"
                                                        >
                                                            <div className="w-1.5 h-1.5 rounded-full bg-violet-500/50 mt-1.5 flex-shrink-0 shadow-[0_0_8px_rgba(139,92,246,0.4)]" />
                                                            <span className="font-mono text-[11px] leading-relaxed text-violet-200/50 whitespace-pre-wrap">
                                                                {line.replace(/^› /, '')}
                                                            </span>
                                                        </motion.div>
                                                    ))}
                                                </div>
                                            </div>

                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                        )}
                    </div>
                    <span className="text-[10px] text-white/20 px-1">
                        {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                </div>
            </div>
        </motion.div>
    );
}

function TypingDots() {
    return (
        <div className="flex items-center ml-1">
            {[1, 2, 3].map((dot) => (
                <motion.div
                    key={dot}
                    className="w-1.5 h-1.5 bg-white/90 rounded-full mx-0.5"
                    initial={{ opacity: 0.3 }}
                    animate={{
                        opacity: [0.3, 0.9, 0.3],
                        scale: [0.85, 1.1, 0.85]
                    }}
                    transition={{
                        duration: 1.2,
                        repeat: Infinity,
                        delay: dot * 0.15,
                        ease: "easeInOut",
                    }}
                    style={{
                        boxShadow: "0 0 4px rgba(255, 255, 255, 0.3)"
                    }}
                />
            ))}
        </div>
    );
}

const rippleKeyframes = `
@keyframes ripple {
  0% { transform: scale(0.5); opacity: 0.6; }
  100% { transform: scale(2); opacity: 0; }
}
`;

if (typeof document !== 'undefined') {
    const style = document.createElement('style');
    style.innerHTML = rippleKeyframes;
    document.head.appendChild(style);
}
