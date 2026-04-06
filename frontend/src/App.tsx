import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { AnimatedAIChat } from './components/ui/animated-ai-chat';
import { Component as LoginPage } from './components/ui/animated-characters-login-page';
import { HeroGeometric as WelcomePage } from './components/ui/shape-landing-hero';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<WelcomePage />} />
        <Route path="/chat" element={
          <div className="lab-bg relative min-h-screen">
            <AnimatedAIChat />
          </div>
        } />
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </Router>
  );
}

export default App;
